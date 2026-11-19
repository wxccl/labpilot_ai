First use
Choose the station profile shared with the managed Runmanager and BLACS. In Operations, click Live context. Compare the sequence, output folder and shot count with Runmanager. Capabilities lists device channels and advertised operations. Use Details for raw receipts.

Run one shot
1. Select the sequence and reduce all scan axes to one shot in Runmanager. Select the analysis routines in Lyse. In LabPilot, check that Analysis reads native_h5.
2. Prepare one shot. For a parameter change or manual BLACS operation, use Import action with a reviewed JSON file, or ask the connected agent to draft it. Record the baseline before changing a static channel.
3. Select the draft and inspect its parameters. Approve selected grants a 15-minute approval. Run next approved dispatches the oldest eligible queue entry; selection alone does not set execution order.
4. Observe selected reads execution evidence. A selected observing task refreshes every 15 seconds. A missing Lyse field keeps quality pending. For an uncertain dispatch, inspect Events before doing anything else. Restore the approved baseline after the test.

Agent setup
Settings > Connect an agent: choose DeepSeek Harness and copy the stdio fields to its MCP settings, or select Codex CLI and run the copied registration command in Anaconda Prompt. Ask the agent to read the current sequence, output and shot count first. Approve and dispatch through the operator interface.

Desktop and language
Settings > Create desktop shortcut installs a profile-bound link on the current Windows user's actual desktop and displays its path. Settings > Chinese switches language immediately. Qt preferences are saved per Windows user.

Suite inspector
Read the Runmanager snapshot for active globals. Load the BLACS inventory, choose a device and read its state. Select a completed task in Operations before opening its Lyse report folder. Use New action to draft one advertised operation. Fill in actual values; placeholders are examples.
