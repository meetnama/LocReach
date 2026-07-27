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
    # Always re-ping on remount; re-arm the parent interval if it was lost.
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

  var port = '{_heartbeat_port}';
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

  // Every Streamlit rerun remounts this iframe — ping immediately so the
  // watchdog never sees a false "tab closed" during Step 1 auto-refresh.
  root.__locreachPing();

  if (!root.__locreachHeartbeatInterval) {{
    root.__locreachHeartbeatInterval = root.setInterval(function() {{
      root.__locreachPing();
    }}, 3000);
    root.document.addEventListener('visibilitychange', function() {{
      if (!root.document.hidden) root.__locreachPing();
    }});
    root.addEventListener('pagehide', root.__locreachSignalClose);
    root.addEventListener('beforeunload', root.__locreachSignalClose);
  }}
  root.__locreachHeartbeat = true;
}})();
</script>
""",
        height=0,
    )

# Custom sidebar links come from inject_theme on each page.
pg = st.navigation(
    [
        st.Page("pages/0_Home.py",     title="Home",              icon="🏠", default=True, url_path="home"),
        st.Page("pages/1_Domains.py",  title="Step 1 · Domains",  icon="🔍", url_path="domains"),
        st.Page("pages/2_People.py",   title="Step 2 · People",   icon="👥", url_path="people"),
        st.Page("pages/3_Emails.py",   title="Step 3 · Emails",   icon="📧", url_path="emails"),
        st.Page("pages/4_Database.py", title="Database",          icon="🗄️", url_path="database"),
    ],
    # Custom sidebar links only — framework top/sidebar nav has been unreliable.
    position="hidden",
)
pg.run()
