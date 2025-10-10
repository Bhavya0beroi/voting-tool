import streamlit as st
import sqlite3
import os
import uuid
from datetime import datetime
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import pandas as pd

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
# IMPORTANT: Set these in your Streamlit secrets (/.streamlit/secrets.toml)
# WRITER_SLACK_CHANNEL_ID = "C0..."
# GRAPHIC_SLACK_CHANNEL_ID = "C0..."
# etc.
SLACK_BOT_TOKEN = st.secrets.get("SLACK_BOT_TOKEN", "")
TEAM_CHANNELS = {
    "Writer": st.secrets.get("WRITER_SLACK_CHANNEL_ID", ""),
    "Graphic Team": st.secrets.get("GRAPHIC_SLACK_CHANNEL_ID", ""),
    "Editor": st.secrets.get("EDITOR_SLACK_CHANNEL_ID", ""),
    "Reindex Team": st.secrets.get("REINDEX_SLACK_CHANNEL_ID", ""),
    "Social Team": st.secrets.get("SOCIAL_SLACK_CHANNEL_ID", ""),
    "Company-Wide": st.secrets.get("COMPANY_WIDE_SLACK_CHANNEL_ID", "") # For company-wide votes
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
    # Projects table
    c.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')
    # Polls (stages) table
    c.execute('''
        CREATE TABLE IF NOT EXISTS polls (
            id TEXT PRIMARY KEY,
            project_id INTEGER,
            team TEXT NOT NULL,
            submitter_name TEXT NOT NULL,
            vote_type TEXT NOT NULL,
            status TEXT NOT NULL, -- 'active', 'completed', 'rejected'
            created_at TEXT NOT NULL,
            content_json TEXT, -- Store file paths, text, links etc as JSON
            FOREIGN KEY (project_id) REFERENCES projects (id)
        )
    ''')
    # Votes table for simple approve/reject/keep/discard
    c.execute('''
        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            poll_id TEXT,
            voter_name TEXT NOT NULL,
            vote_decision TEXT NOT NULL, -- 'Approved', 'Rejected', 'Keep', 'Discard'
            item_id TEXT, -- For voting on specific thumbnails/titles
            FOREIGN KEY (poll_id) REFERENCES polls (id)
        )
    ''')
    # Feedback table for detailed editor reviews
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
    """Saves a single file to the UPLOAD_DIR and returns its path."""
    if uploaded_file:
        file_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}_{uploaded_file.name}")
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return file_path
    return None

def send_slack_notification(team, message):
    """Sends a notification to the appropriate team's Slack channel."""
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

    # --- Project Selection ---
    conn = get_db_connection()
    projects = conn.execute('SELECT * FROM projects').fetchall()
    project_dict = {p['name']: p['id'] for p in projects}
    conn.close()

    new_or_existing = st.radio("Project", ["Existing Project", "New Project"], horizontal=True, label_visibility="collapsed")
    project_id = None
    if new_or_existing == "Existing Project":
        if project_dict:
            project_name = st.selectbox("Select Project", options=project_dict.keys())
            project_id = project_dict[project_name]
        else:
            st.warning("No existing projects. Please create a new one.")
            return
    else:
        project_name = st.text_input("Enter New Project Name")
        if project_name:
            if project_name in project_dict:
                st.error("A project with this name already exists.")
                return
            else: # Create new project on submission
                pass

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
            content['loom_video'] = save_uploaded_file(st.file_uploader("Upload Loom/Explanation Video (Optional)"))

    elif team == "Graphic Team":
        vote_type = st.selectbox("Vote Type", ["Manager Approval", "Team Approval"])
        content['design_notes'] = st.text_area("Design Notes")
        uploaded_files = st.file_uploader("Upload Theme Assets (Multi-file)", accept_multiple_files=True)
        content['assets'] = [save_uploaded_file(f) for f in uploaded_files]
        content['gdrive_link'] = st.text_input("Or paste a Google Drive link (Optional)")

    elif team == "Editor":
        vote_type = st.selectbox("Vote Type", ["First Cut Approval", "Final Video Approval"])
        content['video'] = save_uploaded_file(st.file_uploader("Upload Video", type=['mp4', 'mov']))
        content['gdrive_link'] = st.text_input("Or paste a Google Drive link (Optional)")
        content['notes'] = st.text_area("Notes for Reviewer")

    elif team == "Reindex Team":
        vote_type = st.selectbox("Vote Type", ["Internal Shortlisting", "Company-Wide Final Vote"])
        st.info("For 'Company-Wide' votes, create the poll after shortlisting from the 'Results' page.")
        if vote_type == "Internal Shortlisting":
            uploaded_thumbs = st.file_uploader("Upload All Thumbnail Ideas", accept_multiple_files=True)
            content['thumbnails'] = [save_uploaded_file(f) for f in uploaded_thumbs]
            content['titles'] = st.text_area("Paste All Title Ideas (one per line)")

    elif team == "Social Team":
        vote_type = "Final Post Approval"
        content['format'] = st.selectbox("Select Format", ["Reels", "Static", "Carousel"])
        content['platform'] = st.selectbox("Select Platform", ["Instagram", "LinkedIn"])
        uploaded_asset = st.file_uploader("Upload Final Asset(s)", accept_multiple_files=True)
        content['assets'] = [save_uploaded_file(f) for f in uploaded_asset]
        content['gdrive_link'] = st.text_input("Or paste a Google Drive link (Optional)")
        content['copy'] = st.text_area("Paste Final Copy/Caption")


    if st.button("🚀 Start Vote", use_container_width=True, type="primary"):
        if not all([submitter_name, team, vote_type]) or (new_or_existing == "New Project" and not project_name) or not any(content.values()):
            st.error("Please fill all required fields and upload content.")
            return

        conn = get_db_connection()
        # Handle project creation
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

        # Insert new poll
        poll_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO polls (id, project_id, team, submitter_name, vote_type, status, created_at, content_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (poll_id, project_id, team, submitter_name, vote_type, 'active', datetime.now().isoformat(), pd.io.json.dumps(content))
        )
        conn.commit()
        conn.close()

        # Send Slack notification
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
        return

    for poll in active_polls:
        content = pd.io.json.loads(poll['content_json'])
        with st.expander(f"**{poll['project_name']}** | `{poll['vote_type']}` by {poll['submitter_name']}", expanded=True):
            
            # --- Render Content ---
            if poll['team'] == "Editor" and poll['vote_type'] == "Final Video Approval":
                # Detailed feedback UI
                st.video(content.get('video'))
                st.markdown("---")
                st.subheader("Submit Your Detailed Feedback")
                with st.form(key=f"feedback_form_{poll['id']}"):
                    likes = st.text_area("👍 What did you like?")
                    dislikes = st.text_area("🤔 What could be improved?")
                    score = st.slider("Rate this video (out of 10)", 1, 10, 5)
                    if st.form_submit_button("Submit Feedback", use_container_width=True):
                        if voter_name:
                            conn.execute(
                                "INSERT INTO feedback (poll_id, voter_name, likes, dislikes, score) VALUES (?, ?, ?, ?, ?)",
                                (poll['id'], voter_name, likes, dislikes, score)
                            )
                            conn.commit()
                            st.success("Feedback submitted!")
                        else:
                            st.warning("Please enter your name.")

            elif poll['team'] == "Reindex Team" and poll['vote_type'] == "Internal Shortlisting":
                # Grid-based keep/discard UI
                st.subheader("Titles to Review")
                titles = [t.strip() for t in content.get('titles', '').split('\n') if t.strip()]
                for title in titles:
                    c1, c2, c3 = st.columns([0.6, 0.2, 0.2])
                    c1.text(title)
                    if c2.button("👍 Keep", key=f"keep_title_{poll['id']}_{title}", use_container_width=True):
                        # Logic to add vote
                        pass
                    if c3.button("👎 Discard", key=f"discard_title_{poll['id']}_{title}", use_container_width=True):
                        # Logic to add vote
                        pass
                
                st.subheader("Thumbnails to Review")
                # Add thumbnail review logic here
                st.warning("Reindex Team voting UI is a work in progress.")


            else: # Standard Approve/Reject
                # Display content for other teams
                if 'script_content' in content: st.info(content['script_content'])
                if 'assets' in content and content['assets']:
                    # Filter out None values before trying to display
                    valid_assets = [asset for asset in content['assets'] if asset and os.path.exists(asset)]
                    try:
                        st.image(valid_assets, width=150, caption="Uploaded Assets")
                    except Exception as e:
                        st.error(f"Could not display one or more assets. Error: {e}")

                if 'video' in content and content['video']: st.video(content['video'])
                # Add more content display types as needed...
                st.markdown("---")

                # --- Voting Buttons ---
                cols = st.columns(2)
                if cols[0].button("✅ Approve", key=f"approve_{poll['id']}", use_container_width=True):
                    if voter_name:
                        conn.execute(
                            "INSERT INTO votes (poll_id, voter_name, vote_decision) VALUES (?, ?, ?)",
                            (poll['id'], voter_name, 'Approved')
                        )
                        conn.commit()
                        st.success("Your vote is recorded!")
                    else: st.warning("Please enter your name.")

                if cols[1].button("❌ Reject", key=f"reject_{poll['id']}", use_container_width=True):
                     if voter_name:
                        conn.execute(
                            "INSERT INTO votes (poll_id, voter_name, vote_decision) VALUES (?, ?, ?)",
                            (poll['id'], voter_name, 'Rejected')
                        )
                        conn.commit()
                        st.success("Your vote is recorded!")
                     else: st.warning("Please enter your name.")


            # Finalize Poll
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

            if poll['team'] == "Editor" and poll['vote_type'] == "Final Video Approval":
                feedback = conn.execute("SELECT * FROM feedback WHERE poll_id = ?", (poll['id'],)).fetchall()
                if feedback:
                    scores = [f['score'] for f in feedback]
                    avg_score = sum(scores) / len(scores)
                    st.metric("Average Score", f"{avg_score:.2f} / 10")
                    
                    for item in feedback:
                        with st.expander(f"Feedback from {item['voter_name']} (Score: {item['score']})"):
                            st.write("**👍 Likes:**")
                            st.write(item['likes'])
                            st.write("**🤔 Improvements:**")
                            st.write(item['dislikes'])
                else:
                    st.write("No detailed feedback was submitted for this poll.")
            
            else: # Standard votes display
                votes = conn.execute("SELECT * FROM votes WHERE poll_id = ?", (poll['id'],)).fetchall()
                if votes:
                    df = pd.DataFrame(votes)
                    # Check if 'vote_decision' column exists and is not empty before proceeding
                    if 'vote_decision' in df.columns and not df['vote_decision'].empty:
                        vote_counts = df['vote_decision'].value_counts()
                        st.bar_chart(vote_counts)
                        st.write("#### All Votes:")
                        st.dataframe(df[['voter_name', 'vote_decision']], use_container_width=True)
                    else:
                         st.write("No votes were recorded for this poll.")
                else:
                    st.write("No votes were recorded for this poll.")
    conn.close()

# --- MAIN APP LOGIC ---
def main():
    """Main function to run the Streamlit app."""
    initialize_db()
    
    st.title("🎬 Content Workflow & Voting Tool")

    page = st.sidebar.radio("Navigation", ["Create Vote", "Active Polls", "Results"])

    if page == "Create Vote":
        create_vote_page()
    elif page == "Active Polls":
        active_polls_page()
    elif page == "Results":
        results_page()

if __name__ == "__main__":
    main()
