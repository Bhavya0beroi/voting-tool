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

# --- SECURITY & CONFIGURATION (from secrets.toml) ---
SLACK_BOT_TOKEN = st.secrets.get("SLACK_BOT_TOKEN", "")
TEAM_CHANNELS = {
    "Writer": st.secrets.get("WRITER_SLACK_CHANNEL_ID", ""),
    "Graphic Team": st.secrets.get("GRAPHIC_SLACK_CHANNEL_ID", ""),
    "Editor": st.secrets.get("EDITOR_SLACK_CHANNEL_ID", ""),
    "Reindex Team": st.secrets.get("REINDEX_SLACK_CHANNEL_ID", ""),
    "Social Team": st.secrets.get("SOCIAL_SLACK_CHANNEL_ID", ""),
    "Company-Wide": st.secrets.get("COMPANY_WIDE_SLACK_CHANNEL_ID", "")
}
MANAGER_NAMES = st.secrets.get("MANAGER_NAMES", [])


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
    c.execute('''CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS polls (id TEXT PRIMARY KEY, project_id INTEGER, team TEXT NOT NULL, submitter_name TEXT NOT NULL, vote_type TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, content_json TEXT, FOREIGN KEY (project_id) REFERENCES projects (id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS votes (id INTEGER PRIMARY KEY AUTOINCREMENT, poll_id TEXT, voter_name TEXT NOT NULL, vote_decision TEXT NOT NULL, item_id TEXT, FOREIGN KEY (poll_id) REFERENCES polls (id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, poll_id TEXT, voter_name TEXT NOT NULL, likes TEXT, dislikes TEXT, score INTEGER, FOREIGN KEY (poll_id) REFERENCES polls (id))''')
    conn.commit()
    conn.close()

# --- UTILITY FUNCTIONS ---
def save_uploaded_file(uploaded_file):
    """Saves an uploaded file to the UPLOAD_DIR and returns its path."""
    if uploaded_file:
        file_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}_{uploaded_file.name}")
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return file_path
    return None

def send_slack_notification(team, message):
    """Sends a message to a configured Slack channel."""
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
    project_id = None; project_name = ""
    if new_or_existing == "Existing Project":
        if project_dict:
            project_name = st.selectbox("Select Project", options=project_dict.keys()); project_id = project_dict.get(project_name)
        else: st.warning("No existing projects. Please create a new one."); return
    else: project_name = st.text_input("Enter New Project Name")

    submitter_name = st.text_input("Your Name")
    team = st.selectbox("Select Your Team", ["Writer", "Graphic Team", "Editor", "Reindex Team", "Social Team"])

    content = {}; vote_type = ""; button_label = "🚀 Start Team Vote"
    
    # --- DYNAMIC FORM LOGIC ---
    # This section dynamically builds the form based on the selected team
    
    if team == "Writer":
        vote_type = st.selectbox("Approval Type", ["Writer Team Approval", "Writer Manager Approval"])
        if "Manager Approval" in vote_type: button_label = "📤 Submit for Manager Approval"
        content['script_content'] = st.text_area("Paste Script Here")
        if "Manager Approval" in vote_type:
            uploaded_file = st.file_uploader("Upload Loom/Explanation Video (Optional)")
            content['loom_video'] = save_uploaded_file(uploaded_file)
    
    elif team == "Graphic Team":
        vote_type = st.selectbox("Approval Type", ["Graphic Team Approval", "Graphic Manager Approval"])
        if "Manager Approval" in vote_type: button_label = "📤 Submit for Manager Approval"
        content['design_notes'] = st.text_area("Design Notes")
        uploaded_files = st.file_uploader("Upload Theme Assets (Multi-file)", accept_multiple_files=True)
        content['assets'] = [save_uploaded_file(f) for f in uploaded_files] if uploaded_files else []
        content['gdrive_link'] = st.text_input("Or paste a Google Drive link (Optional)")

    elif team == "Editor":
        vote_type = st.selectbox("Vote Type", ["First Cut Approval", "Final Video Approval"])
        uploaded_file = st.file_uploader("Upload Video", type=['mp4', 'mov'])
        content['video'] = save_uploaded_file(uploaded_file)
        content['notes'] = st.text_area("Notes for Reviewer")

    elif team == "Reindex Team":
        vote_type = "Internal Shortlisting"
        st.subheader("Submit Titles & Thumbnails for Internal Voting")
        if 'title_count' not in st.session_state: st.session_state.title_count = 2
        if 'thumb_count' not in st.session_state: st.session_state.thumb_count = 2
        content['thumbnails'] = {}
        content['titles'] = {}
        for i in range(st.session_state.thumb_count):
            uploaded_file = st.file_uploader(f"Thumbnail Idea {i+1}", key=f"thumb_{i}")
            if uploaded_file: content['thumbnails'][f"Thumbnail {i+1}"] = save_uploaded_file(uploaded_file)
        if st.button("Add Another Thumbnail"): st.session_state.thumb_count += 1; st.rerun()
        for i in range(st.session_state.title_count):
            title_text = st.text_input(f"Title Idea {i+1}", key=f"title_{i}")
            if title_text: content['titles'][f"Title {i+1}"] = title_text
        if st.button("Add Another Title"): st.session_state.title_count += 1; st.rerun()

    elif team == "Social Team":
        vote_type = "Final Post Approval"
        content['format'] = st.selectbox("Select Format", ["Reels", "Static", "Carousel"])
        content['platform'] = st.selectbox("Select Platform", ["Instagram", "LinkedIn"])
        uploaded_asset = st.file_uploader("Upload Final Asset(s)", accept_multiple_files=True)
        content['assets'] = [save_uploaded_file(f) for f in uploaded_asset] if uploaded_asset else []
        content['copy'] = st.text_area("Paste Final Copy/Caption")
    
    st.markdown("---")
    if st.button(button_label, use_container_width=True, type="primary"):
        is_content_valid = any(v for v in content.values() if v)
        if not all([submitter_name, team, vote_type, project_name]) or not is_content_valid:
            st.error("Please fill all required fields and upload content."); return
        conn = get_db_connection()
        if new_or_existing == "New Project":
            try:
                cur = conn.cursor(); cur.execute("INSERT INTO projects (name) VALUES (?)", (project_name,)); project_id = cur.lastrowid; conn.commit()
            except sqlite3.IntegrityError: st.error("Project name already exists."); conn.close(); return
        
        poll_id = str(uuid.uuid4())
        status = 'awaiting_manager_approval' if "Manager Approval" in vote_type else 'active_team_poll'
        conn.execute("INSERT INTO polls (id, project_id, team, submitter_name, vote_type, status, created_at, content_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (poll_id, project_id, team, submitter_name, vote_type, status, datetime.now().isoformat(), json.dumps(content)))
        conn.commit(); conn.close()
        slack_message = f"🗳️ *New Item for Manager Approval!* 🗳️\n*Project:* {project_name}\n*Team:* {team}\n*Submitted by:* {submitter_name}" if status == 'awaiting_manager_approval' else f"🗳️ *New Team Vote Started!* 🗳️\n*Project:* {project_name}\n*Team:* {team}\n*Submitted by:* {submitter_name}"
        send_slack_notification(team, slack_message)
        st.balloons(); st.success("Your submission has been sent for approval!")

# --- UI: PAGE 2 - MANAGER APPROVALS ---
def manager_approval_page():
    st.header("👨‍💼 Manager Approvals", divider='red')
    st.info("Items here require manager sign-off before proceeding to a team-wide vote.")
    voter_name = st.text_input("Enter Your Name to Approve/Reject", key="manager_name_input")

    if not voter_name:
        st.warning("Please enter your name to see and act on these polls.")
        return
    if voter_name not in MANAGER_NAMES:
        st.error("You do not have permission to view this page.")
        return

    conn = get_db_connection()
    manager_polls = conn.execute("SELECT p.*, pr.name as project_name FROM polls p JOIN projects pr ON p.project_id = pr.id WHERE p.status = 'awaiting_manager_approval' ORDER BY p.created_at DESC").fetchall()

    if not manager_polls:
        st.success("✅ No items are currently waiting for manager approval.")
        conn.close(); return

    for poll in manager_polls:
        with st.expander(f"**{poll['project_name']}** | `{poll['vote_type']}` by {poll['submitter_name']}", expanded=True):
            # Render content... (You can add specific content rendering here)
            st.markdown("---")
            cols = st.columns(2)
            if cols[0].button("✅ Approve & Promote to Team Vote", key=f"approve_{poll['id']}", use_container_width=True):
                conn.execute("UPDATE polls SET status = 'completed_manager_approved' WHERE id = ?", (poll['id'],))
                new_poll_id = str(uuid.uuid4())
                team_vote_type = poll['vote_type'].replace(" Manager Approval", " Team Approval")
                conn.execute("INSERT INTO polls (id, project_id, team, submitter_name, vote_type, status, created_at, content_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (new_poll_id, poll['project_id'], poll['team'], poll['submitter_name'], team_vote_type, 'active_team_poll', datetime.now().isoformat(), poll['content_json']))
                conn.commit()
                slack_message = f"👍 *Approved by Manager!* A new vote is now open for the team.\n*Project:* {poll['project_name']}\n*Type:* {team_vote_type}"
                send_slack_notification(poll['team'], slack_message)
                st.success("Approved! A new poll has been created for the team."); st.rerun()
            
            if cols[1].button("❌ Reject", key=f"reject_{poll['id']}", use_container_width=True):
                conn.execute("UPDATE polls SET status = 'completed_manager_rejected' WHERE id = ?", (poll['id'],))
                conn.commit()
                st.error("Item has been rejected."); st.rerun()
    conn.close()

# --- UI: PAGE 3 - TEAM POLLS ---
def team_polls_page():
    st.header("👥 Team Polls", divider='green')
    conn = get_db_connection()
    voter_name = st.text_input("Enter Your Name to Vote", key="team_voter_name")
    
    # Filtering UI
    teams_with_polls = [row['team'] for row in conn.execute("SELECT DISTINCT team FROM polls WHERE status = 'active_team_poll'").fetchall()]
    filter_options = ["All"] + teams_with_polls
    selected_team = st.selectbox("Filter by Team:", filter_options)

    query = "SELECT p.*, pr.name as project_name FROM polls p JOIN projects pr ON p.project_id = pr.id WHERE p.status = 'active_team_poll'"
    params = []
    if selected_team != "All":
        query += " AND p.team = ?"
        params.append(selected_team)
    
    team_polls = conn.execute(query, params).fetchall()

    if not team_polls:
        st.info("🎉 No active team polls for the selected filter."); conn.close(); return

    for poll in team_polls:
        with st.expander(f"**{poll['project_name']}** | `{poll['vote_type']}` by {poll['submitter_name']}", expanded=True):
            # Render content and voting buttons... (similar to previous versions)
            st.markdown("---")
            if st.button("🔒 Close Poll", key=f"close_{poll['id']}", use_container_width=True):
                conn.execute("UPDATE polls SET status = 'completed_team_vote' WHERE id = ?", (poll['id'],))
                conn.commit(); st.rerun()
    conn.close()

# --- UI: PAGE 4 - RESULTS ---
def results_page():
    st.header("🏆 Results & History", divider='orange')
    conn = get_db_connection()
    
    teams_with_results = [row['team'] for row in conn.execute("SELECT DISTINCT team FROM polls WHERE status LIKE 'completed%'").fetchall()]
    filter_options = ["All Teams"] + teams_with_results
    selected_team = st.selectbox("Filter Results by Team:", filter_options)

    query = "SELECT p.*, pr.name as project_name FROM polls p JOIN projects pr ON p.project_id = pr.id WHERE p.status LIKE 'completed%'"
    params = []
    if selected_team != "All Teams":
        query += " AND p.team = ?"
        params.append(selected_team)
    query += " ORDER BY p.created_at DESC"
    
    completed_polls = conn.execute(query, params).fetchall()
    
    if not completed_polls:
        st.info("No completed polls found for the selected filter."); conn.close(); return

    for poll in completed_polls:
        with st.container(border=True):
            status_emoji = "👍" if "approved" in poll['status'] else "👎" if "rejected" in poll['status'] else "🗳️"
            status_text = poll['status'].replace('completed_', '').replace('_', ' ').title()
            st.subheader(f"{status_emoji} {poll['project_name']} - `{poll['vote_type']}`")
            st.caption(f"Status: **{status_text}** | Submitted by {poll['submitter_name']}")
            # Display detailed results logic (bar charts, feedback, etc.)...

    conn.close()

# --- MAIN APP LOGIC ---
def main():
    initialize_db()
    st.title("🎬 Content Workflow & Voting Tool")

    tab1, tab2, tab3, tab4 = st.tabs(["📮 Create Vote", "👨‍💼 Manager Approvals", "👥 Team Polls", "🏆 Results"])

    with tab1: create_vote_page()
    with tab2: manager_approval_page()
    with tab3: team_polls_page()
    with tab4: results_page()

if __name__ == "__main__":
    main()

