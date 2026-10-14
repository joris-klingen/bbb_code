#!/bin/zsh
# Double-click to start the BBB Restyle app and open it in the browser.
# Close this Terminal window (or press Ctrl+C) to stop the app.
cd "$(dirname "$0")"
if curl -s -o /dev/null http://localhost:8765/api/projects; then
  echo "BBB Restyle is already running; opening it in the browser."
  open http://localhost:8765
else
  python3 -m bbb.app
fi
