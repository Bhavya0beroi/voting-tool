import streamlit as st
import sqlite3
import os
import uuid
from datetime import datetime
import pandas as pd
import json
from PIL import UnidentifiedImageError

# ==========================================
# 🔐 CONFIGURATION - EDIT THESE VALUES ONLY
# ==========================================

# Slack Bot Token (starts with xoxb-)
SLACK_BOT_TOKEN = "xoxb-1778615088705-9691584018598-wIW2cLOy9nyTOwE53ZkDnppS"  # ⬅️ REPLACE THIS

# Slack Channel ID where notifications will be sent
SLACK_CHANNEL_ID = "C09L65S88C9"  # ⬅️ REPLACE THIS (e.g., C09L65S88C9)

# Manager Password
MANAGER_PASSWORD = "Learnapp.123"

# Enable/Disable Slack Notifications
ENABLE_SLACK = True  # Set to False to disable Slack temporarily

# ==========================================
# END OF CONFIGURATION
# ==========================================

# --- APP CONFIGURATION ---
st.set_page_config(
    page_title="Learnapp Voting Tool",
    page_icon="🗳️",
    layout="wide",
)

# --- DIRECTORY AND DATABASE SETUP ---
UPLOAD_DIR = "uploads"
DB_NAME = "workflow.db"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)


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
    """Send notification to Slack using Bot Token"""
    
    # Check if Slack is enabled
    if not ENABLE_SLACK:
        st.info(f"📋 Notification (Slack disabled): {message}")
        return
    
    # Check if credentials are configured
    if SLACK_BOT_TOKEN == "xoxb-YOUR-TOKEN-HERE" or SLACK_CHANNEL_ID == "C01234ABCDE":
        st.warning("⚠️ Slack credentials not configured. Please update SLACK_BOT_TOKEN and SLACK_CHANNEL_ID in the code.")
        st.info(f"📋 Notification message: {message}")
        return
    
    try:
        # Import Slack SDK
        from slack_sdk import WebClient
        from slack_sdk.errors import SlackApiError
        
        # Initialize Slack client
        client = WebClient(token=SLACK_BOT_TOKEN)
        
        # Format message with team name
        formatted_message = f"*{team} Team Update*\n{message}"
        
        # Send message
        response = client.chat_postMessage(
            channel=SLACK_CHANNEL_ID,
            text=formatted_message
        )
        
        if response["ok"]:
            st.success("🚀 Notification sent to Slack!")
        else:
            st.error(f"Failed to send Slack notification: {response}")
            
    except ImportError:
        st.error("❌ Slack SDK not installed. Run: pip install slack-sdk")
    except SlackApiError as e:
        error_msg = e.response.get('error', 'Unknown error')
        st.error(f"❌ Slack API Error: {error_msg}")
        
        # Helpful error messages
        if error_msg == "not_authed" or error_msg == "invalid_auth":
            st.info("🔑 Your Bot Token is invalid or expired. Please check SLACK_BOT_TOKEN.")
        elif error_msg == "channel_not_found":
            st.info("📢 Channel not found. Please verify SLACK_CHANNEL_ID is correct.")
        elif error_msg == "missing_scope":
            st.info("🔐 Missing permissions. Add these scopes: chat:write, chat:write.public")
        
        st.caption(f"Message was: {message}")
    except Exception as e:
        st.error(f"❌ Unexpected error: {str(e)}")
        st.caption(f"Message was: {message}")

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
    
    project_name = st.text_input("New Project Name")
    submitter_name = st.text_input("Your Name")
    team = st.selectbox("Select Your Team", ["Writer", "Graphic Team", "Editor", "Reindex Team", "Social Team"])
    
    content = {}; vote_type = ""; button_label = "🚀 Start Team Vote"
    
    if team == "Writer":
        vote_type = st.selectbox("Approval Type", ["Writer Team Approval", "Writer Manager Approval"])
        if "Manager Approval" in vote_type: button_label = "📤 Submit for Manager Approval"
        
        submission_type = st.radio("Submission Type:", ["Paste Script", "Link to Google Doc/PPT"], horizontal=True)
        if submission_type == "Paste Script":
            content['script_content'] = st.text_area("Paste Script Here")
        else:
            content['doc_link'] = st.text_input("Paste Google Doc or PPT Link Here")

        content['writer_notes'] = st.text_area("Notes (Optional)")
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
            if assets or theme_notes: content['themes'].append({'notes': theme_notes, 'assets': assets, 'name': f"Theme {i+1}"})
        
        if st.button("➕ Add Another Theme"): st.session_state.theme_count += 1; st.rerun()

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
            st.error("Please fill all required fields and upload at least one piece of content."); return

        conn = get_db_connection()
        project_id = None
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO projects (name) VALUES (?)", (project_name,))
            project_id = cur.lastrowid
            conn.commit()
        except sqlite3.IntegrityError:
            st.error(f"A project named '{project_name}' already exists. Please choose a unique name.")
            conn.close(); return
        except Exception as e:
            st.error(f"A database error occurred: {e}"); conn.close(); return

        poll_id = str(uuid.uuid4())
        status = 'awaiting_manager_approval' if "Manager Approval" in vote_type else 'active_team_poll'
        conn.execute("INSERT INTO polls (id, project_id, team, submitter_name, vote_type, status, created_at, content_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (poll_id, project_id, team, submitter_name, vote_type, status, datetime.now().isoformat(), json.dumps(content)))
        conn.commit(); conn.close()
        
        if 'attachment_count' in st.session_state: st.session_state.attachment_count = 0
        if 'theme_count' in st.session_state: st.session_state.theme_count = 1
        
        st.balloons(); st.success("Submission successful!")
        send_slack_notification(team, f"🗳️ New submission from {submitter_name} for project '{project_name}' is ready for review.")


# --- UI HELPER FOR RENDERING CONTENT ---
def render_poll_content(content_json):
    content = json.loads(content_json)
    
    def display_image(image_path_or_list, width=None, caption=None):
        try: st.image(image_path_or_list, width=width, caption=caption)
        except (UnidentifiedImageError, FileNotFoundError): st.error("🖼️ Error: Could not display one or more image files.")
        except Exception as e: st.error(f"An error occurred: {e}")

    if 'writer_notes' in content and content['writer_notes']: st.info(f"**Writer's Notes:** {content['writer_notes']}")
    if 'doc_link' in content and content['doc_link']:
        st.markdown(f"**Script Document:** [Open Google Doc/PPT]({content['doc_link']})")
    if 'script_content' in content and content['script_content']: st.info(content['script_content'])
    if 'explanation_attachment' in content and content['explanation_attachment']: 
        col1, col2 = st.columns([2, 1])
        with col1: st.video(content['explanation_attachment'])
    if 'video' in content and content['video']: 
        col1, col2 = st.columns([2, 1])
        with col1: st.video(content['video'])
    if 'themes' in content:
        for theme in content['themes']:
            with st.container(border=True):
                st.subheader(theme.get('name', 'Theme'))
                if theme['notes']: st.caption(theme['notes'])
                if theme['assets']: display_image(theme['assets'], width=150)
    if 'thumbnails' in content:
        st.subheader("Thumbnails"); display_image(list(content['thumbnails'].values()), width=200, caption=list(content['thumbnails'].keys()))
    if 'assets' in content and content['assets']: display_image(content['assets'], width=400)
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
    
    voter_name = st.text_input("Enter Your Name")
    password = st.text_input("Enter Manager Password", type="password")
    
    is_authorized = (password == MANAGER_PASSWORD)

    if not voter_name or not password:
        st.warning("Please enter your name and the manager password to view this page.")
        return
        
    if not is_authorized:
        st.error("Incorrect password. Access denied.")
        return

    st.success(f"Welcome, {voter_name}! You have manager access.")
    
    conn = get_db_connection()
    manager_polls = conn.execute("SELECT p.*, pr.name as project_name FROM polls p JOIN projects pr ON p.project_id = pr.id WHERE p.status = 'awaiting_manager_approval'").fetchall()
    
    if not manager_polls:
        st.info("✅ No items are currently waiting for manager approval.")
    
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

def team_voting_page():
    st.header("👥 Team Voting", divider='green')
    voter_name = st.text_input("Enter Your Name to Vote", key="team_voter_name")
    if not voter_name: st.warning("Please enter your name to see and vote on polls."); return
    
    conn = get_db_connection()
    all_active_polls = conn.execute("SELECT p.*, pr.name as project_name FROM polls p JOIN projects pr ON p.project_id = pr.id WHERE p.status = 'active_team_poll'").fetchall()
    
    polls_to_vote_on = [p for p in all_active_polls if not conn.execute("SELECT id FROM votes WHERE poll_id = ? AND voter_name = ?", (p['id'], voter_name)).fetchone()]
    polls_voted_on = [p for p in all_active_polls if conn.execute("SELECT id FROM votes WHERE poll_id = ? AND voter_name = ?", (p['id'], voter_name)).fetchone()]

    st.subheader("Action Required: Your Polls to Vote On", divider='blue')
    if not polls_to_vote_on:
        st.success("✅ You are all caught up!")
    else:
        poll_options = {f"{p['project_name']} - {p['vote_type']} (by {p['submitter_name']})": p for p in polls_to_vote_on}
        selected_poll_title = st.selectbox("Select a Poll to Vote On:", options=["-- Please select --"] + list(poll_options.keys()))

        if selected_poll_title != "-- Please select --":
            selected_poll = poll_options[selected_poll_title]
            content = json.loads(selected_poll['content_json'])
            
            with st.container(border=True):
                st.markdown(f"### Voting on: {selected_poll_title}")
                
                if selected_poll['vote_type'] == "Internal Shortlisting":
                    with st.form(key=f"reindex_shortlist_form_{selected_poll['id']}"):
                        st.subheader("Thumbnails")
                        thumbnails = content.get('thumbnails', {})
                        thumb_selections = {}
                        if thumbnails:
                            num_thumbnails = len(thumbnails)
                            num_cols = 5
                            thumbnail_items = list(thumbnails.items())
                            for i in range(0, num_thumbnails, num_cols):
                                cols = st.columns(num_cols)
                                row_items = thumbnail_items[i:i + num_cols]
                                for j, (thumb_name, thumb_path) in enumerate(row_items):
                                    with cols[j]:
                                        st.image(thumb_path, use_container_width=True)
                                        thumb_selections[thumb_name] = st.checkbox(f"Keep {thumb_name}", key=f"thumb_cb_{selected_poll['id']}_{thumb_name}")
                        
                        st.markdown("---")
                        st.subheader("Titles")
                        titles = content.get('titles', {})
                        title_selections = {}
                        if titles:
                            for title_name, title_text in titles.items():
                                title_selections[title_name] = st.checkbox(title_text, key=f"title_cb_{selected_poll['id']}_{title_name}")

                        submitted = st.form_submit_button("Submit Selections")
                        if submitted:
                            kept_thumbnails = [name for name, selected in thumb_selections.items() if selected]
                            kept_titles = [name for name, selected in title_selections.items() if selected]
                            for thumb in kept_thumbnails:
                                conn.execute("INSERT INTO votes (poll_id, voter_name, vote_decision, item_id) VALUES (?, ?, ?, ?)", (selected_poll['id'], voter_name, 'Keep', thumb))
                            for title in kept_titles:
                                 conn.execute("INSERT INTO votes (poll_id, voter_name, vote_decision, item_id) VALUES (?, ?, ?, ?)", (selected_poll['id'], voter_name, 'Keep', title))
                            conn.commit()
                            st.success("Your shortlist selections have been saved!"); st.rerun()
                else:
                    render_poll_content(selected_poll['content_json'])
                    st.markdown("---")
                    with st.form(key=f"team_vote_form_{selected_poll['id']}"):
                        decision = st.radio("Your Decision:", ["👍 Approve", "👎 Reject"], horizontal=True)
                        rating = st.slider("Rating", 1, 10, 5)
                        comment = st.text_area("Comments (Optional)")
                        submitted = st.form_submit_button("Submit Vote")
                        if submitted:
                            vote_decision = "Approved" if decision == "👍 Approve" else "Rejected"
                            conn.execute("INSERT INTO votes (poll_id, voter_name, vote_decision, comment, rating) VALUES (?, ?, ?, ?, ?)", (selected_poll['id'], voter_name, vote_decision, comment, rating))
                            conn.commit(); st.success(f"Your '{vote_decision}' vote is recorded!"); st.balloons()
    
    with st.expander("Polls You've Already Voted On"):
        if not polls_voted_on: st.info("You haven't voted on any active polls yet.")
        else:
            for poll in polls_voted_on:
                my_vote = conn.execute("SELECT * FROM votes WHERE poll_id = ? AND voter_name = ?", (poll['id'], voter_name)).fetchone()
                if my_vote: st.markdown(f"**{poll['project_name']}** | `{poll['vote_type']}` - You voted: **{my_vote['vote_decision']}**")
    conn.close()


def results_page():
    st.header("🏆 Results & History", divider='orange')
    conn = get_db_connection()
    
    result_polls = conn.execute("SELECT p.*, pr.name as project_name FROM polls p JOIN projects pr ON p.project_id = pr.id WHERE p.status LIKE 'completed%' OR p.id IN (SELECT DISTINCT poll_id FROM votes)").fetchall()
    
    if not result_polls:
        st.info("No results to show yet. Cast a vote to see live results here."); conn.close(); return

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
                
                if poll['status'] == 'active_team_poll': st.info("Status: Voting in Progress")
                else: st.success(f"Status: {poll['status'].replace('_', ' ').title()}")
                
                st.markdown("---"); st.subheader("📊 Vote Summary")
                
                votes = conn.execute("SELECT * FROM votes WHERE poll_id = ?", (poll['id'],)).fetchall()
                
                if not votes: st.info("No votes have been cast for this poll yet.")
                else:
                    df = pd.DataFrame([dict(row) for row in votes])
                    
                    if poll['vote_type'] == "Internal Shortlisting":
                        st.write("Tally of 'Keep' votes:")
                        keep_counts = df['item_id'].value_counts().reset_index(); keep_counts.columns = ['Item', 'Keep Votes']
                        st.dataframe(keep_counts)
                    else:
                        total_votes = len(df)
                        avg_rating_col, total_votes_col = st.columns(2)
                        if 'rating' in df.columns and pd.to_numeric(df['rating'], errors='coerce').notna().any():
                            avg_rating = pd.to_numeric(df['rating'], errors='coerce').mean()
                            avg_rating_col.metric("Average Team Rating", f"{avg_rating:.1f} / 10")
                        total_votes_col.metric("Total Votes", total_votes)
                        if 'vote_decision' in df.columns:
                            team_votes_df = df[df['vote_decision'].isin(['Approved', 'Rejected'])]
                            if not team_votes_df.empty:
                                vote_counts = team_votes_df['vote_decision'].value_counts()
                                approve_count = vote_counts.get('Approved', 0); reject_count = vote_counts.get('Rejected', 0)
                                approve_col, reject_col = st.columns(2)
                                approve_col.markdown(f"### ✅ Approved: {approve_count}")
                                reject_col.markdown(f"### ❌ Rejected: {reject_count}")
                        if 'comment' in df.columns:
                            st.caption("Comments:")
                            comments_df = df[df['comment'].notna() & (df['comment'] != '')]
                            if not comments_df.empty:
                                for index, vote in comments_df.iterrows():
                                    st.write(f"- **{vote['voter_name']}:** *'{vote['comment']}'*")
                            else: st.write("No comments were left.")

                if poll['status'] == 'active_team_poll' and poll['vote_type'] == "Internal Shortlisting":
                     if st.button("🚀 Promote Shortlist to Final Vote", key=f"promote_{poll['id']}"):
                        st.info("Promotion logic would be implemented here.")
                
                elif poll['status'] == 'active_team_poll':
                    if st.button("🔒 Finalize and Close Poll", key=f"close_from_results_{poll['id']}"):
                        conn.execute("UPDATE polls SET status = 'completed_team_vote' WHERE id = ?", (poll['id'],))
                        conn.commit(); st.rerun()

                if st.button("🔄 Start Revision", key=f"revise_{poll['id']}"):
                    st.session_state['revision_data'] = {
                        'project_name': poll['project_name'], 'submitter_name': poll['submitter_name'],
                        'team': poll['team'], 'parent_poll_id': poll['id']
                    }
                    st.success("Revision started! Go to the '📮 Create Vote' tab now.")
    conn.close()

def main():
    initialize_db()
    st.title("Learnapp Voting Tool")
    
    # Configuration status indicator
    with st.sidebar:
        st.header("⚙️ Configuration")
        if SLACK_BOT_TOKEN == "xoxb-YOUR-TOKEN-HERE":
            st.error("🔴 Slack Not Configured")
        else:
            st.success("🟢 Slack Configured")
        
        st.caption(f"Notifications: {'Enabled' if ENABLE_SLACK else 'Disabled'}")
    
    tab1, tab2, tab3, tab4 = st.tabs(["📮 Create Vote", "👨‍💼 Manager Approvals", "👥 Team Voting", "🏆 Results"])

    with tab1: create_vote_page()
    with tab2: manager_approval_page()
    with tab3: team_voting_page()
    with tab4: results_page()

if __name__ == "__main__":
    main()
