====================================================
  LOCREACH — Setup & Install Guide
====================================================

Run these steps IN ORDER the first time you set up LocReach.

----------------------------------------------------
 MOVING TO A NEW PC
----------------------------------------------------

  >>> See the full guide:  "MOVE TO NEW PC.txt"  (in this folder) <<<

  Short version:
    - Copy the whole Sales_Tool folder to the new PC (any drive/path).
      You may skip venv\ (~500 MB) and .chrome_profile\ (~580 MB) —
      both are rebuilt automatically.
    - On the new PC run, in order:
        1 - Get Python.bat   (tick "Add Python to PATH")
        2 - Get Chrome.bat   (skip if Chrome already installed)
        3 - Get Docker.bat   (optional — only for SearXNG / OpenSERP)
        4 - Install LocReach.bat   (rebuilds the environment)
        6 - Start LocReach.bat     (launch)
    - Your data + login carry over in leads.db and .env.

  Everything is path-independent: the .bat files find their own
  location, and "4 - Install LocReach.bat" rebuilds a venv copied
  from another machine. Full details + troubleshooting are in
  "MOVE TO NEW PC.txt".

----------------------------------------------------
 REQUIRED SOFTWARE
----------------------------------------------------

  1 - Get Python.bat
      Installs Python 3.11+
      Required to run the app.
      Check "Add Python to PATH" during install!

  2 - Get Chrome.bat
      Installs Google Chrome
      Required for Google/Bing Chrome search and LinkedIn scanning.
      Skip if Chrome is already installed.

  3 - Get Docker.bat          [OPTIONAL]
      Installs Docker Desktop
      Needed for SearXNG / OpenSERP (local search engines).
      Skip if you only plan to use Chrome search.

----------------------------------------------------
 INSTALL PYTHON PACKAGES
----------------------------------------------------

  4 - Install LocReach.bat
      Creates the Python virtual environment and
      installs all required packages from requirements.txt
      Run this once after Python is installed,
      and again after any code update.

----------------------------------------------------
 START SEARXNG  (optional but recommended)
----------------------------------------------------

  5 - Start SearXNG.bat
      Starts the local SearXNG search engine via Docker.
      Settings file: <Sales_Tool>\searxng\settings.yml (next to this
      Setup folder — the launcher finds it automatically).
      Run this each time you want to use SearXNG mode.
      Docker Desktop must be open and running first.
      SearXNG runs at: http://localhost:8888

  7 - Start OpenSERP.bat
      Optional free SERP fallback (http://localhost:7000).
      LocReach also auto-starts it when Docker is available.

----------------------------------------------------
 DAILY USE
----------------------------------------------------

  6 - Start LocReach.bat
      Launches the Streamlit app in your browser.
      Run this every session after setup is complete.

----------------------------------------------------
 3-STEP PIPELINE
----------------------------------------------------

  Step 1 - Find & Qualify Domains
      Search → qualify companies for outreach.
      Output: domains table (qualified)

  Step 2 - Find People
      Decision-maker contacts via LinkedIn / search.
      Output: people table

  Step 3 - Find Emails
      Work emails for each person + verification.
      SMTP verification needs dnspython — installed by
      "4 - Install LocReach.bat".
      Output: leads table + Excel export

====================================================
