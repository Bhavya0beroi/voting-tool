import streamlit as st
import sqlite3
import os
import uuid
from datetime import datetime
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import pandas as pd
import json

# --- APP CONFIGURATION ---
st.set_page_config(
    page_title="Team Workflow & Voting Tool",
    page_icon="🗳️",
    layout="wide",
)

# --- DIRECTORY AND DATABASE SETUP ---
UPLOAD_DIR = "uploads"
DB_NAME = "workflow.db"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# --- SLACK CONFIGURATION ---
# This section reads the values from your .streamlit/secrets.toml file
# The change you requested is made in that file, not here.
SLACK_BOT_TOKEN = st.secrets.get("SLACK_BOT_TOKEN", "")
TEAM_CHANNELS = {
    "Writer": st.secrets.get("WRITER_SLACK_CHANNEL_ID", ""),
    "Graphic Team": st.secrets.get("GRAPHIC_SLACK_CHANNEL_ID", ""),
    "Editor": st.secrets.get("EDITOR_SLACK_CHANNEL_ID", ""),
    "Reindex Team": st.secrets.get("REINDEX_SLACK_CHANNEL_ID", ""),
    "Social Team": st.secrets.get("SOCIAL_SLACK_CHANNEL_ID", ""),
    "Company-Wide": st.secrets.get("COMPANY_WIDE_SLACK_CHANNEL_ID", "")
}

# --- DATABASE HELPERS ---
def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_db():
    """Initializes the database with the required tables if they don't exist."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS polls (
            id TEXT PRIMARY KEY,
            project_id INTEGER,
            team TEXT NOT NULL,
            submitter_name TEXT NOT NULL,
            vote_type TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            content_json TEXT,
            FOREIGN KEY (project_id) REFERENCES projects (id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            poll_id TEXT,
            voter_name TEXT NOT NULL,
            vote_decision TEXT NOT NULL,
            item_id TEXT, -- For voting on specific thumbnails/titles
            FOREIGN KEY (poll_id) REFERENCES polls (id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            poll_id TEXT,
            voter_name TEXT NOT NULL,
            likes TEXT,
            dislikes TEXT,
            score INTEGER,
            FOREIGN KEY (poll_id) REFERENCES polls (id)
        )
    ''')
    conn.commit()
    conn.close()

# --- UTILITY FUNCTIONS ---
def save_uploaded_file(uploaded_file):
    if uploaded_file:
        file_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}_{uploaded_file.name}")
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return file_path
    return None

def send_slack_notification(team, message):
    channel_id = TEAM_CHANNELS.get(team)
    if not SLACK_BOT_TOKEN or not channel_id:
        st.warning(f"Slack not configured for {team}. Notification not sent.")
        return
    try:
        client = WebClient(token=SLACK_BOT_TOKEN)
        client.chat_postMessage(channel=channel_id, text=message)
        st.success("🚀 Voting notification sent to Slack!")
    except SlackApiError as e:
        st.error(f"Error sending Slack notification: {e.response['error']}")

# --- UI: PAGE 1 - CREATE VOTE ---
def create_vote_page():
    st.header("📮 Create New Vote", divider='blue')

    conn = get_db_connection()
    projects = conn.execute('SELECT * FROM projects').fetchall()
    project_dict = {p['name']: p['id'] for p in projects}
    conn.close()

    new_or_existing = st.radio("Project", ["Existing Project", "New Project"], horizontal=True, label_visibility="collapsed")
    project_id = None
    project_name = ""
    if new_or_existing == "Existing Project":
        if project_dict:
            project_name = st.selectbox("Select Project", options=project_dict.keys())
            project_id = project_dict.get(project_name)
        else:
            st.warning("No existing projects. Please create a new one.")
            return
    else:
        project_name = st.text_input("Enter New Project Name")

    submitter_name = st.text_input("Your Name")
    team = st.selectbox("Select Your Team", ["Writer", "Graphic Team", "Editor", "Reindex Team", "Social Team"])

    content = {}
    vote_type = ""

    # --- Dynamic Form Generation Based on Team ---
    if team == "Writer":
        vote_type = st.selectbox("Approval Type", ["Founder/Manager Approval", "Team Approval"])
        content['script_type'] = st.selectbox("Script Type", ["Shorts Script", "YouTube Script"])
        content['script_content'] = st.text_area("Paste Script Here")
        if vote_type == "Founder/Manager Approval":
            uploaded_file = st.file_uploader("Upload Loom/Explanation Video (Optional)")
            content['loom_video'] = save_uploaded_file(uploaded_file) if uploaded_file else None

    elif team == "Graphic Team":
        vote_type = st.selectbox("Vote Type", ["Manager Approval", "Team Approval"])
        content['design_notes'] = st.text_area("Design Notes")
        uploaded_files = st.file_uploader("Upload Theme Assets (Multi-file)", accept_multiple_files=True)
        content['assets'] = [save_uploaded_file(f) for f in uploaded_files] if uploaded_files else []
        content['gdrive_link'] = st.text_input("Or paste a Google Drive link (Optional)")

    elif team == "Editor":
        vote_type = st.selectbox("Vote Type", ["First Cut Approval", "Final Video Approval"])
        uploaded_file = st.file_uploader("Upload Video", type=['mp4', 'mov'])
        content['video'] = save_uploaded_file(uploaded_file) if uploaded_file else None
        content['gdrive_link'] = st.text_input("Or paste a Google Drive link (Optional)")
        content['notes'] = st.text_area("Notes for Reviewer")

    elif team == "Reindex Team":
        st.subheader("Submit Titles & Thumbnails for Internal Voting")
        vote_type = "Internal Shortlisting"
        
        if 'title_count' not in st.session_state:
            st.session_state.title_count = 2
        if 'thumb_count' not in st.session_state:
            st.session_state.thumb_count = 2

        content['thumbnails'] = {}
        content['titles'] = {}

        st.markdown("---")
        st.markdown("##### Thumbnail Submissions")
        for i in range(st.session_state.thumb_count):
            uploaded_file = st.file_uploader(f"Thumbnail Idea {i+1}", key=f"thumb_{i}")
            if uploaded_file:
                content['thumbnails'][f"Thumbnail {i+1}"] = save_uploaded_file(uploaded_file)

        if st.button("Add Another Thumbnail", key="add_thumb"):
            st.session_state.thumb_count += 1
            st.rerun()

        st.markdown("---")
        st.markdown("##### Title Submissions")
        for i in range(st.session_state.title_count):
            title_text = st.text_input(f"Title Idea {i+1}", key=f"title_{i}")
            if title_text:
                content['titles'][f"Title {i+1}"] = title_text

        if st.button("Add Another Title", key="add_title"):
            st.session_state.title_count += 1
            st.rerun()

    elif team == "Social Team":
        vote_type = "Final Post Approval"
        content['format'] = st.selectbox("Select Format", ["Reels", "Static", "Carousel"])
        content['platform'] = st.selectbox("Select Platform", ["Instagram", "LinkedIn"])
        uploaded_asset = st.file_uploader("Upload Final Asset(s)", accept_multiple_files=True)
        content['assets'] = [save_uploaded_file(f) for f in uploaded_asset] if uploaded_asset else []
        content['gdrive_link'] = st.text_input("Or paste a Google Drive link (Optional)")
        content['copy'] = st.text_area("Paste Final Copy/Caption")
        
    st.markdown("---")
    if st.button("🚀 Start Vote", use_container_width=True, type="primary"):
        is_content_valid = any(isinstance(v, str) and v.strip() for v in content.values()) or \
                           any(isinstance(v, list) and v for v in content.values()) or \
                           any(isinstance(v, dict) and v for v in content.values())
        
        if not all([submitter_name, team, vote_type, project_name]) or not is_content_valid:
            st.error("Please fill all required fields and upload content.")
            return

        conn = get_db_connection()
        if new_or_existing == "New Project":
            try:
                cur = conn.cursor()
                cur.execute("INSERT INTO projects (name) VALUES (?)", (project_name,))
                project_id = cur.lastrowid
                conn.commit()
            except sqlite3.IntegrityError:
                st.error("Project name already exists.")
                conn.close()
                return
        
        poll_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO polls (id, project_id, team, submitter_name, vote_type, status, created_at, content_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (poll_id, project_id, team, submitter_name, vote_type, 'active', datetime.now().isoformat(), json.dumps(content))
        )
        conn.commit()
        conn.close()

        slack_message = f"🗳️ *New Vote Started!* 🗳️\n*Project:* {project_name}\n*Team:* {team}\n*Type:* {vote_type}\n*Submitted by:* {submitter_name}\nPlease cast your vote in the Workflow Tool."
        send_slack_notification(team, slack_message)
        st.balloons()
        st.success("Your submission is now live for voting!")

# --- UI: PAGE 2 - ACTIVE POLLS ---
def active_polls_page():
    st.header("🗳️ Active Polls", divider='green')
    voter_name = st.text_input("Enter Your Name to Vote", key="voter_name_input")

    conn = get_db_connection()
    active_polls = conn.execute(
        "SELECT polls.*, projects.name as project_name FROM polls JOIN projects ON polls.project_id = projects.id WHERE status = 'active' ORDER BY created_at DESC"
    ).fetchall()

    if not active_polls:
        st.info("🎉 No active polls at the moment. Great work!")
        conn.close()
        return

    for poll in active_polls:
        content = json.loads(poll['content_json'])
        with st.expander(f"**{poll['project_name']}** | `{poll['vote_type']}` by {poll['submitter_name']}", expanded=True):
            
            if poll['team'] == "Reindex Team" and poll['vote_type'] == "Internal Shortlisting":
                if not voter_name:
                    st.warning("Please enter your name above to vote on these items.")
                
                existing_votes = conn.execute("SELECT * FROM votes WHERE poll_id = ?", (poll['id'],)).fetchall()
                
                st.subheader("Thumbnail Shortlisting")
                for thumb_id, thumb_path in content.get('thumbnails', {}).items():
                    if thumb_path and os.path.exists(thumb_path):
                        col1, col2, col3 = st.columns([0.4, 0.3, 0.3])
                        with col1:
                            st.image(thumb_path, caption=thumb_id, use_column_width=True)
                        if col2.button("👍 Keep", key=f"keep_{poll['id']}_{thumb_id}", use_container_width=True):
                            if voter_name:
                                conn.execute("INSERT INTO votes (poll_id, voter_name, vote_decision, item_id) VALUES (?, ?, ?, ?)",
                                             (poll['id'], voter_name, 'Keep', thumb_id))
                                conn.commit()
                                st.rerun()
                        if col3.button("👎 Discard", key=f"discard_{poll['id']}_{thumb_id}", use_container_width=True):
                             if voter_name:
                                conn.execute("INSERT INTO votes (poll_id, voter_name, vote_decision, item_id) VALUES (?, ?, ?, ?)",
                                             (poll['id'], voter_name, 'Discard', thumb_id))
                                conn.commit()
                                st.rerun()

                st.subheader("Title Shortlisting")
                for title_id, title_text in content.get('titles', {}).items():
                    col1, col2, col3 = st.columns([0.6, 0.2, 0.2])
                    with col1:
                        st.info(f"**{title_id}:** {title_text}")
                    if col2.button("👍 Keep", key=f"keep_{poll['id']}_{title_id}", use_container_width=True):
                        if voter_name:
                            conn.execute("INSERT INTO votes (poll_id, voter_name, vote_decision, item_id) VALUES (?, ?, ?, ?)",
                                             (poll['id'], voter_name, 'Keep', title_id))
                            conn.commit()
                            st.rerun()
                    if col3.button("👎 Discard", key=f"discard_{poll['id']}_{title_id}", use_container_width=True):
                        if voter_name:
                            conn.execute("INSERT INTO votes (poll_id, voter_name, vote_decision, item_id) VALUES (?, ?, ?, ?)",
                                             (poll['id'], voter_name, 'Discard', title_id))
                            conn.commit()
                            st.rerun()
                
                st.markdown("---")
                st.write("**Votes Recorded:**")
                votes_df = pd.DataFrame(existing_votes)
                if not votes_df.empty:
                    st.dataframe(votes_df[['voter_name', 'item_id', 'vote_decision']], use_container_width=True)

            elif poll['team'] == "Editor" and poll['vote_type'] == "Final Video Approval":
                st.video(content.get('video'))
                st.markdown("---")
                st.subheader("Submit Your Detailed Feedback")
                with st.form(key=f"feedback_form_{poll['id']}"):
                    likes = st.text_area("👍 What did you like?")
                    dislikes = st.text_area("🤔 What could be improved?")
                    score = st.slider("Rate this video (out of 10)", 1, 10, 5)
                    if st.form_submit_button("Submit Feedback", use_container_width=True):
                        if voter_name:
                            conn.execute("INSERT INTO feedback (poll_id, voter_name, likes, dislikes, score) VALUES (?, ?, ?, ?, ?)", (poll['id'], voter_name, likes, dislikes, score))
                            conn.commit()
                            st.success("Feedback submitted!")
                        else: st.warning("Please enter your name.")

            else: # Standard Approve/Reject
                if 'script_content' in content: st.info(content['script_content'])
                if 'assets' in content and content['assets']:
                    valid_assets = [asset for asset in content['assets'] if asset and os.path.exists(asset)]
                    if valid_assets: st.image(valid_assets, width=150, caption="Uploaded Assets")
                if 'video' in content and content['video']: st.video(content['video'])
                st.markdown("---")
                cols = st.columns(2)
                if cols[0].button("✅ Approve", key=f"approve_{poll['id']}", use_container_width=True):
                    if voter_name:
                        conn.execute("INSERT INTO votes (poll_id, voter_name, vote_decision) VALUES (?, ?, ?)",(poll['id'], voter_name, 'Approved'))
                        conn.commit()
                        st.success("Your vote is recorded!")
                    else: st.warning("Please enter your name.")
                if cols[1].button("❌ Reject", key=f"reject_{poll['id']}", use_container_width=True):
                     if voter_name:
                        conn.execute("INSERT INTO votes (poll_id, voter_name, vote_decision) VALUES (?, ?, ?)", (poll['id'], voter_name, 'Rejected'))
                        conn.commit()
                        st.success("Your vote is recorded!")
                     else: st.warning("Please enter your name.")

            st.markdown("---")
            if st.button("🔒 Close Poll", key=f"close_{poll['id']}", use_container_width=True):
                conn.execute("UPDATE polls SET status = 'completed' WHERE id = ?", (poll['id'],))
                conn.commit()
                st.rerun()

    conn.close()

# --- UI: PAGE 3 - RESULTS ---
def results_page():
    st.header("🏆 Results & History", divider='orange')

    conn = get_db_connection()
    completed_polls = conn.execute(
        "SELECT polls.*, projects.name as project_name FROM polls JOIN projects ON polls.project_id = projects.id WHERE status = 'completed' ORDER BY created_at DESC"
    ).fetchall()
    
    if not completed_polls:
        st.info("No completed polls yet.")
        conn.close()
        return

    for poll in completed_polls:
        with st.container(border=True):
            st.subheader(f"{poll['project_name']} - `{poll['vote_type']}`")
            st.caption(f"Submitted by {poll['submitter_name']} on {datetime.fromisoformat(poll['created_at']).strftime('%Y-%m-%d')}")
            
            votes = conn.execute("SELECT * FROM votes WHERE poll_id = ?", (poll['id'],)).fetchall()
            
            if poll['team'] == "Reindex Team" and poll['vote_type'] == "Internal Shortlisting":
                if votes:
                    df = pd.DataFrame(votes)
                    st.write("#### Shortlisting Results:")
                    results = df.groupby(['item_id', 'vote_decision']).size().unstack(fill_value=0)
                    st.dataframe(results, use_container_width=True)
                else:
                    st.write("No votes were recorded for this poll.")

            elif poll['team'] == "Editor" and poll['vote_type'] == "Final Video Approval":
                feedback = conn.execute("SELECT * FROM feedback WHERE poll_id = ?", (poll['id'],)).fetchall()
                if feedback:
                    scores = [f['score'] for f in feedback]
                    avg_score = sum(scores) / len(scores)
                    st.metric("Average Score", f"{avg_score:.2f} / 10")
                    for item in feedback:
                        with st.expander(f"Feedback from {item['voter_name']} (Score: {item['score']})"):
                            st.write("**👍 Likes:**", item['likes'])
                            st.write("**🤔 Improvements:**", item['dislikes'])
                else: st.write("No detailed feedback was submitted.")
            
            else: # Standard votes display
                if votes:
                    df = pd.DataFrame(votes)
                    if 'vote_decision' in df.columns and not df['vote_decision'].empty:
                        vote_counts = df['vote_decision'].value_counts()
                        st.bar_chart(vote_counts)
                        st.write("#### All Votes:")
                        st.dataframe(df[['voter_name', 'vote_decision']], use_container_width=True)
                    else: st.write("No votes were recorded for this poll.")
                else: st.write("No votes were recorded for this poll.")

    conn.close()

# --- MAIN APP LOGIC ---
def main():
    """Main function to run the Streamlit app."""
    initialize_db()
    
    st.title("🎬 Content Workflow & Voting Tool")

    tab1, tab2, tab3 = st.tabs(["📮 Create Vote", "🗳️ Active Polls", "🏆 Results"])

    with tab1:
        create_vote_page()
    with tab2:
        active_polls_page()
    with tab3:
        results_page()

if __name__ == "__main__":
    main()

