import streamlit as st
import sqlite3
import os
import uuid
from datetime import datetime
import pandas as pd
import json
from PIL import UnidentifiedImageError

# ==========================================
# 🔐 CONFIGURATION - FROM SECRETS
# ==========================================

# Load from secrets.toml
try:
    SLACK_BOT_TOKEN = st.secrets.get("SLACK_BOT_TOKEN", "")
    SLACK_CHANNEL_ID = st.secrets.get("SLACK_CHANNEL_ID", "")
    MANAGER_PASSWORD = st.secrets.get("MANAGER_PASSWORD", "Learnapp.123")
except:
    SLACK_BOT_TOKEN = ""
    SLACK_CHANNEL_ID = ""
    MANAGER_PASSWORD = "Learnapp.123"

# Auto-detect Streamlit app URL
def get_app_url():
    try:
        if 'APP_URL' in st.secrets:
            return st.secrets['APP_URL']
        import os
        if 'STREAMLIT_SERVER_HEADLESS' in os.environ:
            hostname = os.environ.get('HOSTNAME', '')
            if hostname:
                return f"https://{hostname}"
        return "https://voting-tool-y6ctrfdb95wzcik3i8vl6y.streamlit.app"
    except:
        return "https://voting-tool-y6ctrfdb95wzcik3i8vl6y.streamlit.app"

APP_URL = get_app_url()
ENABLE_SLACK = True

# ==========================================
# APP CONFIGURATION
# ==========================================

st.set_page_config(
    page_title="Learnapp Voting Tool",
    page_icon="🗳️",
    layout="wide",
)

UPLOAD_DIR = "uploads"
DB_NAME = "workflow.db"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)


# ==========================================
# DATABASE FUNCTIONS
# ==========================================

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS polls (id TEXT PRIMARY KEY, project_id INTEGER, team TEXT NOT NULL, submitter_name TEXT NOT NULL, vote_type TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, content_json TEXT, parent_poll_id TEXT, FOREIGN KEY (project_id) REFERENCES projects (id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS votes (id INTEGER PRIMARY KEY AUTOINCREMENT, poll_id TEXT, voter_name TEXT NOT NULL, vote_decision TEXT NOT NULL, item_id TEXT, comment TEXT, rating INTEGER, FOREIGN KEY (poll_id) REFERENCES polls (id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, poll_id TEXT, voter_name TEXT NOT NULL, likes TEXT, dislikes TEXT, score INTEGER, FOREIGN KEY (poll_id) REFERENCES polls (id))''')
    conn.commit()
    conn.close()


# ==========================================
# UTILITY FUNCTIONS
# ==========================================

def save_uploaded_file(uploaded_file):
    if uploaded_file:
        file_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}_{uploaded_file.name}")
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return file_path
    return None

def send_slack_notification(team, message, poll_id=None, team_param=None):
    if not ENABLE_SLACK:
        st.info(f"📋 Notification (Slack disabled): {message}")
        return
    
    if not SLACK_BOT_TOKEN or not SLACK_CHANNEL_ID:
        st.warning("⚠️ Slack credentials not configured")
        return
    
    try:
        from slack_sdk import WebClient
        from slack_sdk.errors import SlackApiError
        
        client = WebClient(token=SLACK_BOT_TOKEN)
        
        if poll_id and team_param:
            voting_link = f"{APP_URL}?tab=team-voting&poll={poll_id}&team={team_param}"
            formatted_message = f"*{team} Team Update*\n{message}\n\n👉 <{voting_link}|Click here to vote>"
        else:
            voting_link = f"{APP_URL}?tab=team-voting"
            formatted_message = f"*{team} Team Update*\n{message}\n\n👉 <{voting_link}|Click here to vote>"
        
        response = client.chat_postMessage(channel=SLACK_CHANNEL_ID, text=formatted_message)
        
        if response["ok"]:
            st.success("🚀 Notification sent to Slack!")
        else:
            st.error(f"Failed to send Slack notification")
            
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")


# ==========================================
# DIRECT VOTING PAGE (For Slack Links)
# ==========================================

def team_voting_page_direct():
    st.header("👥 Team Voting", divider='green')
    
    query_params = st.query_params
    specific_poll_id = query_params.get("poll")
    
    voter_name = st.text_input("Enter Your Name to Vote", key="team_voter_name")
    
    if not voter_name:
        st.warning("Please enter your name to see and vote on polls.")
        return
    
    conn = get_db_connection()
    
    poll = conn.execute(
        "SELECT p.*, pr.name as project_name FROM polls p JOIN projects pr ON p.project_id = pr.id WHERE p.status = 'active_team_poll' AND p.id = ?",
        (specific_poll_id,)
    ).fetchone()
    
    if not poll:
        st.error("❌ Poll not found or already closed.")
        conn.close()
        return
    
    already_voted = conn.execute(
        "SELECT id FROM votes WHERE poll_id = ? AND voter_name = ?",
        (poll['id'], voter_name)
    ).fetchone()
    
    if already_voted:
        st.info("✅ You have already voted on this poll!")
        st.balloons()
        conn.close()
        return
    
    st.markdown(f"### 📋 {poll['project_name']}")
    st.caption(f"{poll['vote_type']} by {poll['submitter_name']}")
    st.markdown("---")
    
    content = json.loads(poll['content_json'])
    
    if poll['vote_type'] == "Internal Shortlisting":
        with st.form(key="direct_shortlist"):
            st.subheader("Thumbnails")
            thumbnails = content.get('thumbnails', {})
            thumb_selections = {}
            if thumbnails:
                for thumb_name, thumb_path in thumbnails.items():
                    col1, col2 = st.columns([1, 4])
                    with col1:
                        try:
                            st.image(thumb_path, use_container_width=True)
                        except:
                            st.write("Image")
                    with col2:
                        thumb_selections[thumb_name] = st.checkbox(f"Keep {thumb_name}", key=f"t_{thumb_name}")
            
            st.markdown("---")
            st.subheader("Titles")
            titles = content.get('titles', {})
            title_selections = {}
            if titles:
                for title_name, title_text in titles.items():
                    title_selections[title_name] = st.checkbox(title_text, key=f"title_{title_name}")

            if st.form_submit_button("Submit Selections", type="primary", use_container_width=True):
                for thumb_name, selected in thumb_selections.items():
                    if selected:
                        conn.execute("INSERT INTO votes (poll_id, voter_name, vote_decision, item_id) VALUES (?, ?, ?, ?)",
                                    (poll['id'], voter_name, 'Keep', thumb_name))
                for title_name, selected in title_selections.items():
                    if selected:
                        conn.execute("INSERT INTO votes (poll_id, voter_name, vote_decision, item_id) VALUES (?, ?, ?, ?)",
                                    (poll['id'], voter_name, 'Keep', title_name))
                conn.commit()
                conn.close()
                st.success("✅ Your selections saved!")
                st.balloons()
                st.rerun()
    else:
        render_poll_content(content)
        st.markdown("---")
        with st.form(key="direct_vote"):
            decision = st.radio("Your Decision:", ["👍 Approve", "👎 Reject"], horizontal=True)
            rating = st.slider("Rating", 1, 10, 5)
            comment = st.text_area("Comments (Optional)")
            if st.form_submit_button("Submit Vote", type="primary", use_container_width=True):
                vote_decision = "Approved" if decision == "👍 Approve" else "Rejected"
                conn.execute("INSERT INTO votes (poll_id, voter_name, vote_decision, comment, rating) VALUES (?, ?, ?, ?, ?)",
                            (poll['id'], voter_name, vote_decision, comment, rating))
                conn.commit()
                conn.close()
                st.success(f"✅ Your '{vote_decision}' vote is recorded!")
                st.balloons()


# ==========================================
# UI HELPER FUNCTIONS
# ==========================================

def additional_attachments_form():
    st.markdown("---")
    st.subheader("Additional Attachments (Optional)")
    if 'attachment_count' not in st.session_state:
        st.session_state.attachment_count = 0

    attachments = []
    num_to_render = st.session_state.attachment_count + 1
    
    for i in range(num_to_render):
        with st.container(border=True):
            st.markdown(f"**Attachment {i+1}**")
            title = st.text_input("Attachment Title", key=f"attach_title_{i}")
            notes = st.text_area("Notes", key=f"attach_notes_{i}")
            uploaded_file = st.file_uploader("Upload File", key=f"attach_file_{i}")
            
            if title:
                attachments.append({
                    "title": title,
                    "notes": notes,
                    "file_path": save_uploaded_file(uploaded_file)
                })

    if st.button("➕ Add Another Attachment"):
        st.session_state.attachment_count += 1
        st.rerun()
    
    return attachments

def render_poll_content(content_json):
    if isinstance(content_json, str):
        content = json.loads(content_json)
    else:
        content = content_json
    
    def display_image(image_path_or_list, width=None, caption=None):
        try:
            st.image(image_path_or_list, width=width, caption=caption)
        except:
            st.error("🖼️ Could not display image")

    if 'writer_notes' in content and content['writer_notes']:
        st.info(f"**Writer's Notes:** {content['writer_notes']}")
    if 'doc_link' in content and content['doc_link']:
        st.markdown(f"**Script Document:** [Open Link]({content['doc_link']})")
    if 'script_content' in content and content['script_content']:
        st.info(content['script_content'])
    if 'explanation_attachment' in content and content['explanation_attachment']:
        try:
            st.video(content['explanation_attachment'])
        except:
            pass
    if 'video' in content and content['video']:
        try:
            st.video(content['video'])
        except:
            pass
    if 'themes' in content:
        for theme in content['themes']:
            with st.container(border=True):
                st.subheader(theme.get('name', 'Theme'))
                if theme.get('notes'):
                    st.caption(theme['notes'])
                if theme.get('assets'):
                    display_image(theme['assets'], width=150)
    if 'thumbnails' in content and content['thumbnails']:
        st.subheader("Thumbnails")
        display_image(list(content['thumbnails'].values()), width=200)
    if 'assets' in content and content['assets']:
        display_image(content['assets'], width=400)
    if 'copy' in content and content['copy']:
        st.info(content['copy'])


# ===========================================================================
# MAIN PAGES
# ===========================================================================

def create_vote_page():
    st.header("📮 Create New Vote", divider='blue')
    
    project_name = st.text_input("New Project Name")
    submitter_name = st.text_input("Your Name")
    team = st.selectbox("Select Your Team", ["Writer", "Graphic Team", "Editor", "Reindex Team", "Social Team"])
    
    content = {}
    vote_type = ""
    button_label = "🚀 Start Team Vote"
    
    if team == "Writer":
        vote_type = st.selectbox("Approval Type", ["Writer Team Approval", "Writer Manager Approval"])
        if "Manager Approval" in vote_type:
            button_label = "📤 Submit for Manager Approval"
        
        submission_type = st.radio("Submission Type:", ["Paste Script", "Link to Google Doc/PPT"], horizontal=True)
        if submission_type == "Paste Script":
            content['script_content'] = st.text_area("Paste Script Here")
        else:
            content['doc_link'] = st.text_input("Paste Google Doc or PPT Link Here")

        content['writer_notes'] = st.text_area("Notes (Optional)")
        uploaded_file = st.file_uploader("Upload Loom Video or PPT (Optional)", type=['mp4', 'mov', 'ppt', 'pptx'])
        content['explanation_attachment'] = save_uploaded_file(uploaded_file)
    
    elif team == "Graphic Team":
        if 'theme_count' not in st.session_state:
            st.session_state.theme_count = 1
        vote_type = st.selectbox("Approval Type", ["Graphic Team Approval", "Graphic Manager Approval"])
        if "Manager Approval" in vote_type:
            button_label = "📤 Submit for Manager Approval"
        
        content['themes'] = []
        for i in range(st.session_state.theme_count):
            st.markdown(f"--- \n ### Theme {i+1}")
            theme_notes = st.text_area(f"Design Notes for Theme {i+1}", key=f"notes_{i}")
            uploaded_files = st.file_uploader(f"Upload Assets for Theme {i+1}", accept_multiple_files=True, key=f"files_{i}", type=['png', 'jpg', 'jpeg'])
            assets = [save_uploaded_file(f) for f in uploaded_files] if uploaded_files else []
            if assets or theme_notes:
                content['themes'].append({'notes': theme_notes, 'assets': assets, 'name': f"Theme {i+1}"})
        
        if st.button("➕ Add Another Theme"):
            st.session_state.theme_count += 1
            st.rerun()

    elif team == "Editor":
        vote_type = st.selectbox("Vote Type", ["First Cut Approval", "Final Video Approval"])
        uploaded_file = st.file_uploader("Upload Video", type=['mp4', 'mov', 'avi'])
        content['video'] = save_uploaded_file(uploaded_file)
        content['notes'] = st.text_area("Notes for Reviewer")

    elif team == "Reindex Team":
        vote_type = "Internal Shortlisting"
        button_label = "Start Internal Shortlisting"
        st.subheader("Submit Titles & Thumbnails for Internal Voting")
        
        content['thumbnails'] = {}
        content['titles'] = {}
        
        st.markdown("---")
        uploaded_thumbnails = st.file_uploader(
            "Upload All Thumbnail Ideas",
            accept_multiple_files=True,
            key="reindex_thumbs_bulk",
            type=['png', 'jpg', 'jpeg']
        )
        if uploaded_thumbnails:
            for i, uploaded_file in enumerate(uploaded_thumbnails):
                content['thumbnails'][f"Thumbnail {i+1}"] = save_uploaded_file(uploaded_file)

        st.markdown("---")
        titles_text = st.text_area("Paste All Title Ideas (one title per line)")
        if titles_text:
            titles_list = [line.strip() for line in titles_text.split('\n') if line.strip()]
            for i, title in enumerate(titles_list):
                content['titles'][f"Title {i+1}"] = title

    elif team == "Social Team":
        vote_type = "Final Post Approval"
        content['format'] = st.selectbox("Select Format", ["Reels", "Static", "Carousel"])
        content['platform'] = st.selectbox("Select Platform", ["Instagram", "LinkedIn"])
        uploaded_asset = st.file_uploader("Upload Final Asset(s)", accept_multiple_files=True, type=['png', 'jpg', 'jpeg', 'mp4', 'mov'])
        content['assets'] = [save_uploaded_file(f) for f in uploaded_asset] if uploaded_asset else []
        content['copy'] = st.text_area("Paste Final Copy/Caption")

    if team != "Graphic Team":
        content['additional_attachments'] = additional_attachments_form()
    
    st.markdown("---")
    if st.button(button_label, use_container_width=True, type="primary"):
        is_content_valid = any(v for k, v in content.items() if v and k not in ['themes', 'additional_attachments', 'thumbnails', 'titles', 'doc_link']) or \
                           ('doc_link' in content and content['doc_link']) or \
                           ('themes' in content and any(t['assets'] or t['notes'] for t in content['themes'])) or \
                           ('thumbnails' in content and content['thumbnails']) or \
                           ('additional_attachments' in content and content['additional_attachments'])

        if not all([submitter_name, project_name]) or not is_content_valid:
            st.error("Please fill all required fields")
            return

        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO projects (name) VALUES (?)", (project_name,))
            project_id = cur.lastrowid
            conn.commit()
        except sqlite3.IntegrityError:
            st.error(f"Project '{project_name}' already exists")
            conn.close()
            return
        except Exception as e:
            st.error(f"Database error: {e}")
            conn.close()
            return

        poll_id = str(uuid.uuid4())
        status = 'awaiting_manager_approval' if "Manager Approval" in vote_type else 'active_team_poll'
        conn.execute("INSERT INTO polls (id, project_id, team, submitter_name, vote_type, status, created_at, content_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
                    (poll_id, project_id, team, submitter_name, vote_type, status, datetime.now().isoformat(), json.dumps(content)))
        conn.commit()
        conn.close()
        
        if 'attachment_count' in st.session_state:
            st.session_state.attachment_count = 0
        if 'theme_count' in st.session_state:
            st.session_state.theme_count = 1
        
        st.balloons()
        st.success("Submission successful!")
        
        team_param = team.lower().replace(" ", "-")
        send_slack_notification(team, f"🗳️ New submission from {submitter_name} for project '{project_name}' is ready for review.", poll_id, team_param)


def manager_approval_page():
    st.header("👨‍💼 Manager Approvals", divider='red')
    
    voter_name = st.text_input("Enter Your Name")
    password = st.text_input("Enter Manager Password", type="password")
    
    if not voter_name or not password:
        st.warning("Please enter your name and password")
        return
        
    if password != MANAGER_PASSWORD:
        st.error("Incorrect password")
        return

    st.success(f"Welcome, {voter_name}!")
    
    conn = get_db_connection()
    manager_polls = conn.execute("SELECT p.*, pr.name as project_name FROM polls p JOIN projects pr ON p.project_id = pr.id WHERE p.status = 'awaiting_manager_approval'").fetchall()
    
    if not manager_polls:
        st.info("✅ No items waiting for approval")
    
    for poll in manager_polls:
        with st.expander(f"**{poll['project_name']}** | `{poll['vote_type']}`", expanded=True):
            render_poll_content(poll['content_json'])
            with st.form(key=f"mgr_form_{poll['id']}"):
                comment = st.text_area("Comments (Required for Rejection)")
                approve_button = st.form_submit_button("✅ Approve")
                reject_button = st.form_submit_button("❌ Reject")
                if approve_button:
                    conn.execute("UPDATE polls SET status = 'completed_manager_approved' WHERE id = ?", (poll['id'],))
                    new_poll_id = str(uuid.uuid4())
                    team_vote_type = poll['vote_type'].replace(" Manager Approval", " Team Approval")
                    conn.execute("INSERT INTO polls (id, project_id, team, submitter_name, vote_type, status, created_at, content_json, parent_poll_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", 
                                (new_poll_id, poll['project_id'], poll['team'], poll['submitter_name'], team_vote_type, 'active_team_poll', datetime.now().isoformat(), poll['content_json'], poll['id']))
                    conn.execute("INSERT INTO votes (poll_id, voter_name, vote_decision, comment) VALUES (?, ?, ?, ?)", (poll['id'], voter_name, 'Manager Approved', comment))
                    conn.commit()
                    st.success("Approved!")
                    st.rerun()
                if reject_button:
                    if not comment:
                        st.error("Comment required")
                    else:
                        conn.execute("UPDATE polls SET status = 'completed_manager_rejected' WHERE id = ?", (poll['id'],))
                        conn.execute("INSERT INTO votes (poll_id, voter_name, vote_decision, comment) VALUES (?, ?, ?, ?)", (poll['id'], voter_name, 'Manager Rejected', comment))
                        conn.commit()
                        st.error("Rejected")
                        st.rerun()
    conn.close()


def team_voting_page():
    st.header("👥 Team Voting", divider='green')
    
    voter_name = st.text_input("Enter Your Name to Vote", key="team_voter_name")
    
    if not voter_name:
        st.warning("Please enter your name")
        return
    
    conn = get_db_connection()
    all_active_polls = conn.execute("SELECT p.*, pr.name as project_name FROM polls p JOIN projects pr ON p.project_id = pr.id WHERE p.status = 'active_team_poll'").fetchall()
    
    polls_to_vote_on = [p for p in all_active_polls if not conn.execute("SELECT id FROM votes WHERE poll_id = ? AND voter_name = ?", (p['id'], voter_name)).fetchone()]
    polls_voted_on = [p for p in all_active_polls if conn.execute("SELECT id FROM votes WHERE poll_id = ? AND voter_name = ?", (p['id'], voter_name)).fetchone()]

    st.subheader("Action Required: Your Polls to Vote On", divider='blue')
    
    if not polls_to_vote_on:
        st.success("✅ All caught up!")
    else:
        st.caption(f"You have {len(polls_to_vote_on)} poll(s)")
        poll_options = {f"{p['project_name']} - {p['vote_type']} (by {p['submitter_name']})": p for p in polls_to_vote_on}
        selected_poll_title = st.selectbox("Select a Poll:", options=["-- Please select --"] + list(poll_options.keys()))

        if selected_poll_title != "-- Please select --":
            selected_poll = poll_options[selected_poll_title]
            content = json.loads(selected_poll['content_json'])
            
            with st.container(border=True):
                st.markdown(f"### Voting on: {selected_poll_title}")
                render_poll_content(content)
                st.markdown("---")
                with st.form(key=f"vote_form_{selected_poll['id']}"):
                    decision = st.radio("Your Decision:", ["👍 Approve", "👎 Reject"], horizontal=True)
                    rating = st.slider("Rating", 1, 10, 5)
                    comment = st.text_area("Comments (Optional)")
                    if st.form_submit_button("Submit Vote", type="primary", use_container_width=True):
                        vote_decision = "Approved" if decision == "👍 Approve" else "Rejected"
                        conn.execute("INSERT INTO votes (poll_id, voter_name, vote_decision, comment, rating) VALUES (?, ?, ?, ?, ?)", 
                                    (selected_poll['id'], voter_name, vote_decision, comment, rating))
                        conn.commit()
                        st.success(f"✅ '{vote_decision}' recorded!")
                        st.balloons()
    
    with st.expander("Polls You've Already Voted On"):
        if not polls_voted_on:
            st.info("No votes yet")
        else:
            for poll in polls_voted_on:
                my_vote = conn.execute("SELECT * FROM votes WHERE poll_id = ? AND voter_name = ?", (poll['id'], voter_name)).fetchone()
                if my_vote:
                    st.markdown(f"**{poll['project_name']}** - You voted: **{my_vote['vote_decision']}**")
    conn.close()


def results_page():
    st.header("🏆 Results & History", divider='orange')
    conn = get_db_connection()
    
    result_polls = conn.execute(
        "SELECT p.*, pr.name as project_name FROM polls p JOIN projects pr ON p.project_id = pr.id WHERE p.id IN (SELECT DISTINCT poll_id FROM votes) ORDER BY p.created_at DESC"
    ).fetchall()
    
    if not result_polls:
        st.info("No results yet")
        conn.close()
        return

    teams_with_results = sorted(list(set([poll['team'] for poll in result_polls])))
    team_filter_options = ["All Teams"] + teams_with_results
    selected_team = st.selectbox("Filter by Team:", team_filter_options, key="results_team_filter")

    if selected_team == "All Teams":
        projects_with_results = sorted(list(set([poll['project_name'] for poll in result_polls])))
    else:
        projects_with_results = sorted(list(set([poll['project_name'] for poll in result_polls if poll['team'] == selected_team])))
    
    project_filter_options = ["All Projects"] + projects_with_results
    selected_project = st.selectbox("Filter by Project:", project_filter_options, key="results_project_filter")

    for poll in result_polls:
        team_match = (selected_team == "All Teams" or poll['team'] == selected_team)
        project_match = (selected_project == "All Projects" or poll['project_name'] == selected_project)

        if team_match and project_match:
            with st.container(border=True):
                st.subheader(f"{poll['project_name']} - `{poll['vote_type']}`")
                
                if poll['status'] == 'active_team_poll':
                    st.info("Status: Voting in Progress")
                else:
                    st.success(f"Status: {poll['status'].replace('_', ' ').title()}")
                
                st.markdown("---")
                st.subheader("📊 Vote Summary")
                
                votes = conn.execute("SELECT * FROM votes WHERE poll_id = ?", (poll['id'],)).fetchall()
                
                if not votes:
                    st.info("No votes yet")
                else:
                    df = pd.DataFrame([dict(row) for row in votes])
                    
                    if poll['vote_type'] == "Internal Shortlisting":
                        st.write("Tally of 'Keep' votes:")
                        keep_counts = df['item_id'].value_counts().reset_index()
                        keep_counts.columns = ['Item', 'Keep Votes']
                        st.dataframe(keep_counts)
                    else:
                        total_votes = len(df)
                        col1, col2 = st.columns(2)
                        if 'rating' in df.columns:
                            avg_rating = pd.to_numeric(df['rating'], errors='coerce').mean()
                            col1.metric("Average Rating", f"{avg_rating:.1f}/10")
                        col2.metric("Total Votes", total_votes)
                        
                        if 'vote_decision' in df.columns:
                            team_votes = df[df['vote_decision'].isin(['Approved', 'Rejected'])]
                            if not team_votes.empty:
                                vote_counts = team_votes['vote_decision'].value_counts()
                                approve_count = vote_counts.get('Approved', 0)
                                reject_count = vote_counts.get('Rejected', 0)
                                c1, c2 = st.columns(2)
                                c1.markdown(f"### ✅ Approved: {approve_count}")
                                c2.markdown(f"### ❌ Rejected: {reject_count}")

                if poll['status'] == 'active_team_poll':
                    if st.button("🔒 Finalize and Close Poll", key=f"close_{poll['id']}"):
                        conn.execute("UPDATE polls SET status = 'completed_team_vote' WHERE id = ?", (poll['id'],))
                        
                        final_votes = conn.execute("SELECT * FROM votes WHERE poll_id = ?", (poll['id'],)).fetchall()
                        if final_votes:
                            votes
