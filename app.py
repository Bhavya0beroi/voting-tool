import streamlit as st
import sqlite3
import os
import uuid
from datetime import datetime
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import pandas as pd
import json
from PIL import UnidentifiedImageError

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

# --- UTILITY FUNCTIONS ---
def save_uploaded_file(uploaded_file):
    if uploaded_file:
        file_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}_{uploaded_file.name}")
        with open(file_path, "wb") as f: f.write(uploaded_file.getbuffer())
        return file_path
    return None

def send_slack_notification(team, message):
    channel_id = TEAM_CHANNELS.get(team)
    if not SLACK_BOT_TOKEN or not channel_id:
        st.warning(f"Slack not configured for {team}. Notification not sent."); return
    try:
        client = WebClient(token=SLACK_BOT_TOKEN)
        client.chat_postMessage(channel=channel_id, text=message)
        st.success("🚀 Voting notification sent to Slack!")
    except SlackApiError as e: st.error(f"Error sending Slack notification: {e.response['error']}")

# --- UI HELPER FOR DYNAMIC ATTACHMENTS ---
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
                    "title": title, "notes": notes, "file_path": save_uploaded_file(uploaded_file)
                })

    if st.button("➕ Add Another Attachment"):
        st.session_state.attachment_count += 1; st.rerun()
    
    return attachments

# --- UI: PAGE 1 - CREATE VOTE ---
def create_vote_page():
    st.header("📮 Create New Vote", divider='blue')
    
    conn = get_db_connection(); projects = conn.execute('SELECT * FROM projects').fetchall()
    project_dict = {p['name']: p['id'] for p in projects}
    conn.close()
    
    project_options = list(project_dict.keys()) + ["Create New Project"]
    project_name = st.selectbox("Select Project", options=project_options)
    
    if project_name == "Create New Project":
        project_name = st.text_input("Enter New Project Name", key="new_project_name_input")
    
    project_id = project_dict.get(project_name)
    submitter_name = st.text_input("Your Name")
    team = st.selectbox("Select Your Team", ["Writer", "Graphic Team", "Editor", "Reindex Team", "Social Team"])
    
    content = {}; vote_type = ""; button_label = "🚀 Start Team Vote"
    
    if team == "Writer":
        vote_type = st.selectbox("Approval Type", ["Writer Team Approval", "Writer Manager Approval"])
        if "Manager Approval" in vote_type: button_label = "📤 Submit for Manager Approval"
        content['script_content'] = st.text_area("Paste Script Here")
        uploaded_file = st.file_uploader("Upload Loom Video or PPT (Optional)", type=['mp4', 'mov', 'ppt', 'pptx'])
        content['explanation_attachment'] = save_uploaded_file(uploaded_file)
    
    elif team == "Graphic Team":
        if 'theme_count' not in st.session_state: st.session_state.theme_count = 1
        vote_type = st.selectbox("Approval Type", ["Graphic Team Approval", "Graphic Manager Approval"])
        if "Manager Approval" in vote_type: button_label = "📤 Submit for Manager Approval"
        
        content['themes'] = []
        for i in range(st.session_state.theme_count):
            st.markdown(f"--- \n ### Theme {i+1}")
            theme_notes = st.text_area(f"Design Notes for Theme {i+1}", key=f"notes_{i}")
            uploaded_files = st.file_uploader(f"Upload Assets for Theme {i+1}", accept_multiple_files=True, key=f"files_{i}", type=['png', 'jpg', 'jpeg'])
            assets = [save_uploaded_file(f) for f in uploaded_files] if uploaded_files else []
            if assets or theme_notes: content['themes'].append({'notes': theme_notes, 'assets': assets})
        
        if st.button("➕ Add Another Theme"): st.session_state.theme_count += 1; st.rerun()

    elif team == "Editor":
        vote_type = st.selectbox("Vote Type", ["First Cut Approval", "Final Video Approval"])
        uploaded_file = st.file_uploader("Upload Video", type=['mp4', 'mov', 'avi'])
        content['video'] = save_uploaded_file(uploaded_file)
        content['notes'] = st.text_area("Notes for Reviewer")

    elif team == "Reindex Team":
        vote_type = "Internal Shortlisting"
        st.subheader("Submit Titles & Thumbnails for Internal Voting")
        if 'title_count' not in st.session_state: st.session_state.title_count = 2
        if 'thumb_count' not in st.session_state: st.session_state.thumb_count = 2
        content['thumbnails'] = {}; content['titles'] = {}
        for i in range(st.session_state.thumb_count):
            uploaded_file = st.file_uploader(f"Thumbnail Idea {i+1}", key=f"thumb_{i}", type=['png', 'jpg', 'jpeg'])
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
        uploaded_asset = st.file_uploader("Upload Final Asset(s)", accept_multiple_files=True, type=['png', 'jpg', 'jpeg', 'mp4', 'mov'])
        content['assets'] = [save_uploaded_file(f) for f in uploaded_asset] if uploaded_asset else []
        content['copy'] = st.text_area("Paste Final Copy/Caption")

    if team != "Graphic Team":
        content['additional_attachments'] = additional_attachments_form()
    
    st.markdown("---")
    if st.button(button_label, use_container_width=True, type="primary"):
        is_content_valid = any(v for k, v in content.items() if v and k not in ['themes', 'additional_attachments']) or \
                           ('themes' in content and any(t['assets'] or t['notes'] for t in content['themes'])) or \
                           ('additional_attachments' in content and content['additional_attachments'])

        if not all([submitter_name, project_name]) or not is_content_valid:
            st.error("Please fill all required fields and upload at least one piece of content."); return

        conn = get_db_connection()
        if not project_id and project_name: # Create new project
            try:
                cur = conn.cursor(); cur.execute("INSERT INTO projects (name) VALUES (?)", (project_name,)); project_id = cur.lastrowid; conn.commit()
            except sqlite3.IntegrityError: st.error("Project name already exists."); conn.close(); return

        poll_id = str(uuid.uuid4())
        status = 'awaiting_manager_approval' if "Manager Approval" in vote_type else 'active_team_poll'
        conn.execute("INSERT INTO polls (id, project_id, team, submitter_name, vote_type, status, created_at, content_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (poll_id, project_id, team, submitter_name, vote_type, status, datetime.now().isoformat(), json.dumps(content)))
        conn.commit(); conn.close()
        st.session_state.attachment_count = 0
        st.balloons(); st.success("Submission successful!")
        send_slack_notification(team, f"🗳️ New submission from {submitter_name} for project '{project_name}' is ready for review.")


# --- UI HELPER FOR RENDERING CONTENT ---
def render_poll_content(content_json):
    content = json.loads(content_json)
    
    def display_image(image_path_or_list, width=None, caption=None):
        try:
            st.image(image_path_or_list, width=width, caption=caption)
        except (UnidentifiedImageError, FileNotFoundError):
            st.error("🖼️ Error: Could not display one or more image files. They may be corrupt or missing.")
        except Exception as e: st.error(f"An error occurred while displaying an image: {e}")

    if 'script_content' in content and content['script_content']: st.info(content['script_content'])
    if 'explanation_attachment' in content and content['explanation_attachment']: st.video(content['explanation_attachment'])
    if 'video' in content and content['video']: st.video(content['video'])
    if 'themes' in content:
        for i, theme in enumerate(content['themes']):
            with st.container(border=True):
                st.subheader(f"Theme {i+1}")
                if theme['notes']: st.caption(theme['notes'])
                if theme['assets']: display_image(theme['assets'], width=150)
    if 'thumbnails' in content:
        st.subheader("Thumbnails"); display_image(list(content['thumbnails'].values()), width=200, caption=list(content['thumbnails'].keys()))
    if 'titles' in content:
        st.subheader("Titles"); st.table(pd.DataFrame(content['titles'].values(), index=content['titles'].keys(), columns=["Title"]))
    if 'assets' in content and content['assets']: display_image(content['assets'])
    if 'copy' in content and content['copy']: st.info(content['copy'])
    if 'additional_attachments' in content and content['additional_attachments']:
        st.markdown("---"); st.subheader("Additional Attachments")
        for attachment in content['additional_attachments']:
            with st.container(border=True):
                st.markdown(f"**{attachment['title']}**")
                if attachment['notes']: st.caption(attachment['notes'])
                if attachment['file_path']:
                    try:
                        st.download_button(label=f"Download {os.path.basename(attachment['file_path'])}", data=open(attachment['file_path'], "rb").read(), file_name=os.path.basename(attachment['file_path']))
                    except Exception as e: st.error(f"Could not load file: {e}")

def manager_approval_page():
    st.header("👨‍💼 Manager Approvals", divider='red')
    voter_name = st.text_input("Enter Your Name to Approve/Reject", key="manager_name_input")
    if not voter_name: st.warning("Please enter your name."); return
    if voter_name not in MANAGER_NAMES: st.error("You do not have permission to view this page."); return
    
    conn = get_db_connection()
    manager_polls = conn.execute("SELECT p.*, pr.name as project_name FROM polls p JOIN projects pr ON p.project_id = pr.id WHERE p.status = 'awaiting_manager_approval'").fetchall()
    
    for poll in manager_polls:
        with st.expander(f"**{poll['project_name']}** | `{poll['vote_type']}`", expanded=True):
            render_poll_content(poll['content_json'])
            
            with st.form(key=f"manager_vote_form_{poll['id']}"):
                comment = st.text_area("Comments (Required for Rejection)")
                approve_button = st.form_submit_button("✅ Approve & Promote")
                reject_button = st.form_submit_button("❌ Reject")

                if approve_button:
                    conn.execute("UPDATE polls SET status = 'completed_manager_approved' WHERE id = ?", (poll['id'],))
                    new_poll_id = str(uuid.uuid4())
                    team_vote_type = poll['vote_type'].replace(" Manager Approval", " Team Approval")
                    conn.execute("INSERT INTO polls (id, project_id, team, submitter_name, vote_type, status, created_at, content_json, parent_poll_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (new_poll_id, poll['project_id'], poll['team'], poll['submitter_name'], team_vote_type, 'active_team_poll', datetime.now().isoformat(), poll['content_json'], poll['id']))
                    conn.execute("INSERT INTO votes (poll_id, voter_name, vote_decision, comment) VALUES (?, ?, ?, ?)", (poll['id'], voter_name, 'Manager Approved', comment))
                    conn.commit(); st.success("Approved and promoted!"); st.rerun()

                if reject_button:
                    if not comment: st.error("A comment is required to reject.")
                    else:
                        conn.execute("UPDATE polls SET status = 'completed_manager_rejected' WHERE id = ?", (poll['id'],))
                        conn.execute("INSERT INTO votes (poll_id, voter_name, vote_decision, comment) VALUES (?, ?, ?, ?)", (poll['id'], voter_name, 'Manager Rejected', comment))
                        conn.commit(); st.error("Submission has been rejected."); st.rerun()
    conn.close()

def team_polls_page():
    st.header("👥 Team Polls", divider='green')
    voter_name = st.text_input("Enter Your Name to Vote", key="team_voter_name")
    if not voter_name: st.warning("Please enter your name to vote."); return
    
    conn = get_db_connection()
    team_polls = conn.execute("SELECT p.*, pr.name as project_name FROM polls p JOIN projects pr ON p.project_id = pr.id WHERE p.status = 'active_team_poll'").fetchall()
    
    for poll in team_polls:
        with st.expander(f"**{poll['project_name']}** | `{poll['vote_type']}` by {poll['submitter_name']}", expanded=True):
            render_poll_content(poll['content_json'])
            st.markdown("---")

            with st.form(key=f"team_vote_form_{poll['id']}"):
                comment = st.text_area("Comments (Optional)")
                rating = st.slider("Rating", 1, 10, 5)
                
                cols = st.columns(2)
                approve_button = cols[0].form_submit_button("👍 Approve")
                reject_button = cols[1].form_submit_button("👎 Reject")

                if approve_button:
                    conn.execute("INSERT INTO votes (poll_id, voter_name, vote_decision, comment, rating) VALUES (?, ?, ?, ?, ?)", (poll['id'], voter_name, 'Approved', comment, rating))
                    conn.commit(); st.success("Your 'Approve' vote is recorded!"); st.rerun()

                if reject_button:
                    conn.execute("INSERT INTO votes (poll_id, voter_name, vote_decision, comment, rating) VALUES (?, ?, ?, ?, ?)", (poll['id'], voter_name, 'Rejected', comment, rating))
                    conn.commit(); st.warning("Your 'Reject' vote is recorded."); st.rerun()

            if st.button("🔒 Close Poll", key=f"close_{poll['id']}"):
                conn.execute("UPDATE polls SET status = 'completed_team_vote' WHERE id = ?", (poll['id'],)); conn.commit(); st.rerun()
    conn.close()

def results_page():
    st.header("🏆 Results & History", divider='orange')
    conn = get_db_connection()
    completed_polls = conn.execute("SELECT p.*, pr.name as project_name FROM polls p JOIN projects pr ON p.project_id = pr.id WHERE status LIKE 'completed%'").fetchall()
    
    for poll in completed_polls:
        with st.container(border=True):
            st.subheader(f"{poll['project_name']} - `{poll['vote_type']}`")
            render_poll_content(poll['content_json'])
            
            st.markdown("---"); st.subheader("📊 Vote Summary")
            votes = conn.execute("SELECT * FROM votes WHERE poll_id = ?", (poll['id'],)).fetchall()
            if votes:
                df = pd.DataFrame(votes)
                if 'rating' in df.columns and pd.to_numeric(df['rating'], errors='coerce').notna().any():
                    avg_rating = pd.to_numeric(df['rating'], errors='coerce').mean()
                    st.metric("Average Team Rating", f"{avg_rating:.1f} / 10")
                vote_counts = df['vote_decision'].value_counts(); st.bar_chart(vote_counts)
                st.caption("Comments:")
                for vote in votes:
                    if vote['comment']: st.write(f"- **{vote['voter_name']}:** *'{vote['comment']}'*")
            else: st.info("No votes or feedback were recorded for this poll.")

            if st.button("🔄 Start Revision", key=f"revise_{poll['id']}"):
                st.session_state['revision_data'] = {
                    'project_name': poll['project_name'], 'submitter_name': poll['submitter_name'],
                    'team': poll['team'], 'parent_poll_id': poll['id']
                }
                st.success("Revision started! Go to the '📮 Create Vote' tab now.")
    conn.close()

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

