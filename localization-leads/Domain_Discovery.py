"""
Domain_Discovery.py — LocReach app entry point.

Defines the 3-step navigation and hands off to each page.
No business logic lives here.
"""
import os

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="LocReach — B2B Lead Generation",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded",
)

_heartbeat_port = os.environ.get("LOCREACH_HEARTBEAT_PORT", "").strip()
# Only when local launcher (run_app.py) sets LOCREACH_HEARTBEAT_PORT.
# Cloud Render runs Streamlit directly — no watchdog, and 127.0.0.1:8502 is noise.
if _heartbeat_port:
    # Heartbeat MUST live on window.parent, not this components.html iframe.
    # Step 1 auto-refreshes remount this iframe every ~1.5s; an iframe-scoped
    # setInterval dies on each remount and the run_app.py watchdog then kills
    # Streamlit (Connection error) even though the tab is still open.
    components.html(
        f"""
<script>
(function() {{
  var root;
  try {{
    root = window.parent;
    void root.document; // confirm same-origin
  }} catch (e) {{
    root = window;
  }}
  if (root.__locreachHeartbeat) return;
  root.__locreachHeartbeat = true;

  var port = '{_heartbeat_port}';
  // Define ping ON the parent so it survives this iframe being destroyed
  // on every Streamlit rerun.
  root.__locreachPing = function() {{
    try {{
      fetch('http://127.0.0.1:' + port + '/heartbeat', {{
        method: 'POST',
        mode: 'cors',
        cache: 'no-store',
      }}).catch(function() {{}});
    }} catch (e) {{}}
  }};
  root.__locreachSignalClose = function() {{
    try {{
      navigator.sendBeacon('http://127.0.0.1:' + port + '/closing');
    }} catch (e) {{}}
  }};

  root.__locreachPing();
  root.setInterval(function() {{ root.__locreachPing(); }}, 3000);
  root.document.addEventListener('visibilitychange', function() {{
    if (!root.document.hidden) root.__locreachPing();
  }});
  // Real tab/window close only — never bind to this iframe.
  root.addEventListener('pagehide', root.__locreachSignalClose);
  root.addEventListener('beforeunload', root.__locreachSignalClose);
}})();
</script>
""",
        height=0,
    )

pg = st.navigation(
    [
        st.Page("pages/0_Home.py",     title="Home",              icon="🏠", default=True),
        st.Page("pages/1_Domains.py",  title="Step 1 · Domains",  icon="🔍"),
        st.Page("pages/2_People.py",   title="Step 2 · People",   icon="👥"),
        st.Page("pages/3_Emails.py",   title="Step 3 · Emails",   icon="📧"),
        st.Page("pages/4_Database.py", title="Database",          icon="🗄️"),
    ],
    position="top",
)
pg.run()
