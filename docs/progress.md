# Progress

## 27 September 2026: work started

- The product is specified in [spec.md](spec.md) and [architecture.md](architecture.md). The stack mirrors Quantix.
- Development runs use `TAWREED_HOME` pointed at a scratch folder.

## 27 September 2026: design directions

- Three visual directions are on the private design canvas "Tawreed Design Directions": A Blueprint Ledger, B Desert
  Stone, C Graphite Precision. Each shows the packages workspace (light and dark) with the agent panel and an
  uncertain-assignment decision, plan approval in Arabic, and AI connections.
- The engineer chose none of them: Tawreed is a minimal tool, not a whole app. Drop a BOQ and the work starts; four
  tabs (Home, History, Settings, About). Thmanyah Sans for Arabic. For English the engineer turned down Calibri
  and left the choice among four light open fonts to Claude: Figtree, the most readable at small sizes and the
  closest match to Thmanyah Sans. Headings in Light, body in Regular.
- The canvas now holds the minimal design: drop, working with one decision, Arabic plan approval, revision ready
  (dark) and Settings. The Arabic board is a picture rendered locally with the real font, because the Thmanyah
  licence forbids uploading the font files anywhere.
- Thmanyah files stay out of git (`ui/src/fonts/thmanyah/` is ignored) and ship only inside the compiled app.

## 27 September 2026: skeleton

- **Service:** FastAPI, SQLAlchemy and Alembic under `~/.tawreed` (`TAWREED_HOME` overrides), with a per-launch
  access token on every route except `/health`. Projects start from dropped files: Tawreed keeps an unchanged copy
  of each, named by its content hash; the same file twice is kept once; one unusable file refuses the whole drop.
  Settings (language, theme) and About. Errors carry stable codes the interface translates.
- **Interface:** the four tabs, the drop zone with recent projects, the open project (editable name, files, the
  five-step line, and the no-AI notice, which is the real state until connections exist), History, Settings and
  About. English and Arabic with full right-to-left layout, Arabic plural forms and Latin digits; light, dark and
  system themes. Figtree is bundled; Thmanyah is registered only when its local files exist.
- **Desktop:** a thin Tauri 2 window; drops are handled by the page, so they behave the same in the browser. The dev
  port is 1430 because Quantix uses 1420, so both can run at once.
- **Checks:** 30 service tests, 19 interface tests, typecheck, Ruff and Clippy pass; the production build works with
  and without the Thmanyah files. In the browser, a synthetic CSV and PDF were dropped onto the real service in a
  scratch data folder, then Arabic, dark mode, History and About were checked.
- **Found and fixed:** Escape while renaming still saved the name; English file names in the Arabic view aligned to
  the wrong side; on Windows, stopping the dev server left the service running, because the venv's `python.exe` is
  a launcher (the dev plugin now stops the whole process tree; Quantix's plugin has the same gap).

## 27 September 2026: the Tawreed logo

- The logo is the "T" monogram with one source beam and two routed outputs; `desktop/app-icon.svg` is the gold
  source. In the header the same mark is drawn in the text colour beside the name, so it follows light, dark and
  Arabic. The browser tab uses the gold mark.

## 27 September 2026: AI connections

- **Connections:** Anthropic, OpenAI, Google, xAI and an OpenAI-compatible address, through Pydantic AI. A key is
  kept only after the service lists its models (an OpenAI-compatible service that can't list them is proved by the
  model check instead). Keys live in `~/.tawreed/auth.json`, which is re-locked to the current user after every write
  (Windows: inheritance removed, only the user's security ID keeps access; elsewhere 0600). The API returns only
  the last four characters.
- **Model check:** the model must hand back a one-off code through a tool call; then it is asked to read a number
  from an image, which records whether it can read scanned pages. Tawreed only works with a model that passed.
- **Settings:** the AI Tawreed works with (only checked models are offered), the connections (choose a model,
  check, remove) and adding a connection. Failures arrive as codes and read plainly in English and Arabic.
  Removing the connection in use clears the choice. Home's notice now points to Settings and disappears once an AI
  is chosen.
- **Not yet:** ChatGPT/Codex and Grok subscriptions come with the MCP bridge (M7), since their check needs it.
  Consent records come with the agent (M5), which is the first thing that sends project data.
- **Checks:** 45 service tests (no test reaches a real provider), 28 interface tests, typecheck and Ruff pass. In
  the browser, a fake key sent to Anthropic's real API came back as "The key was refused", with nothing stored.
  Found and fixed: in Arabic, the show-key button covered the start of the key.

## 27 September 2026: reading BOQ files (service side)

- **Readers:** Excel, legacy .xls and ODS through calamine (the real 1.4 MB test BOQ reads in 0.3 s; openpyxl took
  29 s); CSV in UTF-8 or the Arabic Windows code page, delimiter detected; PDFs through PDFium as lines of words with
  their positions, Arabic in reading order (lam-alef ligatures fixed); images and scanned pages marked to be read
  from the page image. Password-protected and damaged files are reported with a reason.
- **Background reading:** new files are read one at a time after a drop; a restart resumes; one bad file never stops
  the reader. Each page's content is kept as JSON beside Tawreed's copy; page images are drawn once and kept.
- **Ledger:** the extractor turns a page and an agent-proposed layout (sheet columns, or PDF column positions with
  how descriptions run on) into items with their exact values, cell or line references and the nearest headings;
  headers, notes and totals are recognised; everything skipped is reported. Rows read from a page image are marked
  for checking. Overlap fingerprints note when a new file repeats or revises an earlier one.
- **Checks:** 82 service tests, Ruff. Synthetic English, Arabic and locked PDF fixtures are generated by
  `service/tests/fixtures/make_pdfs.py`.

## 27 September 2026: reading BOQ files (interface)

- **Files:** each file in an open project says where reading has got to (reading, how many sheets or pages, or that
  it couldn't be read, with a sentence on what to do). The project is asked again every second while anything is
  being read, and "Read" in the step line is marked as the current step.
- **Preview:** a read file opens beneath its name. Sheets show as a grid with Excel's row numbers and column letters,
  every cell exactly as read (no rounding or grouping), 200 rows at a time; hidden sheets are labelled. PDF pages and
  images show as pictures one page at a time; a page with no text says it will be read from the image and checked.
  Page pictures are fetched like every other request, so they will carry the same access in the installed app.
- **Found and fixed:** dragging a page picture inside Tawreed dropped it back into the project as a new file (the
  browser offers a dragged picture as a file). The drop area now ignores drags that start inside the window.
- **Checks:** 82 service tests, 33 interface tests, typecheck, Ruff and Clippy. In the browser, synthetic workbook,
  English and Arabic PDFs, a scan and a locked PDF were read in a scratch data folder and previewed in English and
  Arabic.
- **Next:** the agent (M5).

## 27 September 2026: the agent

- **Worker:** one agent per project on a background thread, a turn at a time (30 model requests at most), each
  turn's context rebuilt from the records: the files and what was done with each page, the approved packages,
  coverage, the engineer's rules, what waits for them, what they decided, the conversation and what is new. A
  project gets a turn when the engineer wrote or answered, when its last turn was cut short, or when there is work
  it can do without waiting; after 15 turns without hearing from the engineer it pauses. Stop takes effect between
  steps. An AI failure that usually clears is retried twice; otherwise the project pauses with a plain reason.
- **Tools:** list and read files (sheet cells with Excel's rows and columns; PDF words with their positions; page
  pictures for scans), lay out sheets and PDF pages, transcribe scans, set pages aside, list items, propose the plan,
  place items by number and range, flag an uncertain item, check the work, ask to publish, message and ask the
  engineer. File text reaches the model fenced as data. No tool can answer for the engineer.
- **Gates:** consent before a project's content first goes to a service (Tawreed raises it; the card names the
  service); overlap when a new file repeats an earlier one (Tawreed raises it with a suggestion; a revision carries
  each unchanged item's package over, and the engineer's placements stay the engineer's); the plan (keep, rename,
  merge, split or remove packages); uncertain items (the choice can become a rule for the project or all projects);
  questions; publishing (recorded; writing the revision is next).
- **Packages:** every item has at most one assignment row, so it can't be in two packages. Items have short numbers
  within the project and packages codes ("03") that are never given again. The engineer edits directly: create,
  rename, merge, remove, move items; the agent never moves an item the engineer placed.
- **Interface:** the step line follows the real stage; the one decision waiting (with how many more), the
  conversation with the engineer's answers and Tawreed's notices, the message box and Stop; a packages summary and a
  packages view with each item's values as the file states them and a link that opens the file at that item (its
  row marked, or its box outlined on the page). Rules for all projects are listed in Settings. In Arabic, names set
  into a sentence are isolated so Latin file and sheet names don't reorder the words around them.
- **Found and fixed:** the database upgrade deleted every extracted item. SQLite alters a table by rebuilding it,
  and with foreign keys on, dropping the old projects and files tables cascaded into their items. Migrations now run
  with foreign keys off and the references are checked afterwards; a test upgrades a database with items in it.
  Also: package codes were reused after a merge; the plan card tagged every package of a first plan as new.
- **Checks:** 98 service tests (the agent end to end through every gate with a scripted model; stop, consent
  declined, AI failure, long run, document text fenced), 40 interface tests, typecheck, Ruff. In the browser, the
  real service with the scripted model went through consent, plan, an uncertain item and the publish request, in
  English and Arabic. Not yet run against a real AI service: that sends data out, so it waits for the engineer.
- **Next:** publishing the revision (M6).

## 27 September 2026: publishing a revision

- **What is written:** the master workbook (cover, package index with item counts and amounts, one sheet per
  package), one workbook per package, the decision log (the engineer's decisions, every placement with who made it
  and why, the rules, how each page was read) and the coverage check (items in use against items placed, the files'
  amounts against the packages', each total a file states beside its items' own sum, and every item with its
  package). Items appear under their headings, each with its source ("Tower BOQ.xlsx › Div.03 › row 10").
- **Values as the source states them:** a value the source wrote as a number goes out as that number, shown grouped
  with its own decimals, so nothing is rounded; anything else goes out as its text. A package's total is left out
  when none of its items has an amount, so unpriced work never reads as priced at nothing. A project whose items are
  mostly Arabic gets Arabic labels and right-to-left sheets. Sheets print landscape, one page wide, with the column
  headings repeated and page numbers.
- **All or nothing:** the workbooks are written into a staging folder, the master is read back and each package's
  items compared with the ledger, a manifest records every file's SHA-256, and only then does the folder become
  `Rev NN`. A failure leaves nothing behind and the publish request still waiting. A revision is never overwritten.
- **Interface:** approving publishing writes the revision; the project then shows it (its files, Open folder,
  Export… as a zip download) and every step as done; earlier revisions are listed, and History shows each project's
  latest.
- **Found and fixed:** after publishing, the agent was told to "check the work and ask to publish" again and did so
  at once; it now knows when the latest revision holds the current work, and its publish request is refused then.
- **Checks:** 105 service tests, 41 interface tests, typecheck, Ruff, Clippy. Workbooks were exported to PDF through
  Excel and looked at in English and Arabic; in the browser, a scripted project was published and shown.
- **Next:** ChatGPT/Codex and Grok subscriptions through their official clients (M7).

## 27 September 2026: subscriptions (stopped for the engineer's decision)

The plan runs ChatGPT/Codex and Grok through their official clients with the client's own shell, file and web tools
off and Tawreed's MCP bridge as the only tool server, and stops to report if a client can't be restricted that way.
Each client was run against a fake model endpoint on this machine that recorded exactly which tools it offered the
model, with the client's home folder in a scratch location: no subscription was used and no project data left the
machine.

- **The bridge works.** An MCP server serving Tawreed's 16 agent tools over stdio, for one project, with the same
  checks; refusals come back as tool errors. It is kept on the local branch `wip/m7-subscription-bridge`, not on
  main, because nothing uses it yet. It takes about 6 s to start (imports).
- **Codex 0.153.4:** `--ignore-user-config`, a read-only sandbox, an empty working folder and `--disable` for its
  shell, exec, image, multi-agent, apps, plugins, browser and computer-use features (plus web search off) leave only
  `request_user_input`, and `apply_patch` (file editing) for real model names. Two problems remain: the user's
  `~/.agents/skills` list is put into every prompt, and Tawreed's MCP tools never reached the model's tool list in
  these runs (Codex defers MCP tools behind a tool search this setup doesn't show). Not shown to be restricted.
- **Grok 1.0.30:** headless `-p` with an explicit allowlist `--tools "search_tool,use_tool"` offers only those two
  meta-tools; an *empty* allowlist offers all 25 built-in tools, terminal and file tools included. MCP servers from
  the user's own Grok config load alongside Tawreed's (reachable through `use_tool`) and would need denying by name
  (`--deny "MCPTool(name__*)"`); Claude and Cursor compatibility is on by default and would bring in the user's
  Claude MCP servers, hooks and personal instruction files unless switched off by environment variables. It can be
  restricted, but only by a long list of settings whose defaults can change between versions.
- **Not tested:** a real signed-in run, which uses the engineer's subscription.

## 27 September 2026: the Windows installer

- **Package:** `npm run package` freezes the service with PyInstaller (one folder, about 100 MB; the migration
  scripts and every dependency's package metadata ship with it) and builds an NSIS installer for the current user
  (`Tawreed_0.1.0_x64-setup.exe`, 53 MB). The interface, Figtree and, on this machine, Thmanyah Sans are embedded
  in the executable; the service is its only resource.
- **Installed app:** the desktop shell starts the service hidden on a free port with a fresh token and a log in the
  app's log folder, and answers the interface's `api` scheme by forwarding each request with the token, so the
  page never holds it. The service runs with `--exit-with-stdin`: the app holds that pipe, so the service stops when
  the app closes and also when it is killed.
- **Release:** `npm run release` writes `SHA256SUMS.txt` beside the installer, says whether Thmanyah is embedded,
  and prints the `gh release create --draft` command. Release builds are made on the engineer's machine for the
  font licence; nothing has been published.
- **Checks:** 106 service tests (including the service stopping when its input closes), 41 interface tests,
  typecheck, Ruff and Clippy. The frozen service was run on its own and read a workbook, a PDF and a scan. The
  release executable was run from the build folder on a scratch data folder: it started its service, the page
  listed the scratch project through the proxy, Arabic rendered in Thmanyah Sans right to left, and closing or
  killing the app stopped the service. The installer itself was built but not installed on this machine.

## 27 September 2026: Grok subscription dropped

- At the engineer's request, the Grok subscription is out of scope; the ChatGPT subscription through Codex stays.
  xAI API keys are unaffected.

## 27 September 2026: Codex drives Tawreed's tools

- A real run on the engineer's ChatGPT subscription, on a synthetic project, passed: Codex found Tawreed's tools,
  called `list_files` and `read_sheet` successfully, answered correctly, and used no other tool.
- What it takes, beyond the lockdown recorded above: `mcp_servers.tawreed.required=true`, so the session waits for
  the bridge and its tools are searchable from the start (Codex hides MCP tools behind `tool_search`, which only
  covers servers ready when the session starts); `mcp_servers.tawreed.default_tools_approval_mode="approve"`, so
  Tawreed's own tools, and only they, run without an approval prompt nobody is there to answer; and an empty
  standard input, or `codex exec` waits for more input. Left in place: `request_user_input`, the MCP resource
  helpers, and `apply_patch`, which the read-only sandbox stops from writing.
- **Next:** Codex as a connection in Settings and as a way to run the agent's turns.

## 28 September 2026: ChatGPT through Codex

- **How it runs:** the service serves the agent's tools over MCP at `/mcp` and the model check's at `/mcp-check`.
  Each Codex run gets a one-time token, passed in an environment variable; the endpoint answers nothing else, not
  even the service's own token. `codex exec` runs locked down as recorded above, with the prompt on standard input.
  Turns stop at once on Stop and after 20 minutes at most; a signed-out or failing Codex pauses the project with a
  plain reason. This replaced the stdio bridge: no tool-server process starts for each turn.
- **Settings:** ChatGPT (Codex) needs no key. Settings shows whether Codex is installed and signed in, opens Codex's
  own sign-in, lists the account's models from Codex's catalogue, and checks a model through `/mcp-check` (a one-off
  code, and a number read from an attached image).
- **Checks:** 112 service tests (six for Codex, with a stand-in for the client against the real service on a real
  port), 42 interface tests, typecheck, Ruff, Clippy.
- **Real run** on the engineer's subscription, on a synthetic project in a scratch data folder: the model check
  passed in 12 s and read the image. The agent then read the workbook, laid out both item sheets, set the rates sheet
  aside and proposed two packages (one turn, 39 s); after approval it placed all 5 items and asked to publish (22 s);
  Rev 00 was published, and the agent wrote to the engineer without asking to publish again. No tool call was
  refused and no other tool was used.

## 28 September 2026: the first real BOQ, formulas, and packages for pricing

- **Real run** (the engineer's El Far BOQ, 15 sheets, through Codex on their subscription): 320 items read, 11
  packages proposed and approved, every item placed, Rev 00 published; every sheet's stated totals equal its items,
  and the packages total 56,566,112.47, the same as the file.
- **Found and fixed:** sheets that state a total per section were reported as differing from their items; each
  sheet's totals are now added up and compared with its items. Excel's float noise from formula cells showed as long
  decimals; computed amounts are shown to the cent.
- **Formulas:** at the engineer's request the workbooks now calculate in Excel: an amount is `=Qty*Rate` wherever
  that is the source's own amount (to a hundredth of a cent; otherwise the source's figure stays), each package's
  total is `=SUM(...)`, the index refers to each package's total, the cover adds up the index, and the coverage
  check's differences are formulas. Checked by Excel on the El Far workbooks: the cover computes 56,566,112.47,
  303 items are formulas, 8 keep their figure, no errors.
- **Packages for pricing:** at publishing the engineer chooses whether package workbooks show rates and amounts.
  Without them the rates are empty and every amount is `=Qty*Rate`, so a supplier's rates price the package; the
  master always shows them. The revision records the choice.
- **Publishing again:** the agent still won't ask to publish what the latest revision already holds, unless the
  engineer has written since, so the same work can go out once with rates and once for pricing. Seen in the
  app: asked in the El Far project, the agent (through Codex) raised the publish card with the rates choice.
- **Both ways on El Far, checked in Excel:** Rev 01 with rates (every one of the 311 amounts equals Rev 00's source
  figure, the cover computes 56,566,112.47, no errors); Rev 02 without rates, then priced as a supplier would with
  the source's rates. That found two items the BOQ prices but leaves out of its amounts (supply-only panels, an
  additional cable), which the without-rates workbooks had turned into =Qty*Rate, adding 7.8 million a supplier's
  price would count. Fixed: such items keep an empty amount. Package amounts in the manifest and the coverage
  check's totals are now recorded to the cent rather than with Excel's float noise.
- **Checks:** 115 service tests, 42 interface tests, typecheck, Ruff, Clippy.

## 28 September 2026: a fixed workflow instead of a conversation

- **Decision (the engineer):** no talking to an agent. Tawreed is a static workflow: the AI does the reading,
  planning and placing as fixed steps with no conversation, runs on its own to each gate, and the engineer corrects
  by editing directly or by running a step again with a note.
- **Service:** `tawreed/agent/` became `tawreed/workflow/`. `next_step` picks Read (per file), Plan or Place from the
  records; each run gets only its step's tools (Codex too: a run's token refuses other steps' tools). The chat tools,
  the agent's questions and `request_publish` are gone: Tawreed raises the publish card itself and shows what the
  revision holds, computed. New routes: Continue, Redo (read a file or page again, place a package or everything
  again, with a note), Publish again, and a sheet's columns or a page set aside by the engineer. A plan can be
  approved as the engineer edited it. Migration 0005 keeps a stopped project stopped and drops the messages and the
  agent's questions.
- **Interface:** the conversation and message box are gone. A status line says what runs, with Stop, or why the
  work paused, with Continue; below the decision card, what the engineer decided so far. The plan card edits the
  plan; Packages has Place again; a file's preview says how each page was read, with Columns…, Set aside and Read
  again….
- **Checked on the El Far BOQ, through Codex:** Place again on one package with a note (the run used only
  `list_items` and `place_items`); the Columns editor on the Facade sheet; Rev 03 and Rev 04 published without rates.
  This found and fixed: a publish card left up after the work changed; a page read again losing its placements
  (three Facade items came back in another package, since put back); items read again moving out of file order in
  the workbooks; and a file preview showing two sheets' controls at once. Rev 04 priced in Excel with the source's
  rates matches every package to the cent, apart from the source's own rounding in eight amounts (0.30 in all).
- **Checks:** 123 service tests, 44 interface tests, typecheck, Ruff, Clippy.

## 28 September 2026: Thmanyah Serif Display for Arabic headings

- **Decision (the engineer):** Arabic headings use Thmanyah Serif Display, from the same Thmanyah family; body text
  stays in Thmanyah Sans and English stays in Figtree.
- **Interface:** a `font-heading` style (Figtree, then Thmanyah Serif Display, then Thmanyah Sans) on the light
  headings: the page titles, the project name, the drop title, the decision title, Packages and the published
  revision. Its files sit beside Thmanyah Sans in the gitignored `ui/src/fonts/thmanyah/`; About credits both.
- **Checked:** in the browser, an Arabic heading loads Serif Display Light while the text under it stays in Sans;
  the production build embeds both families.

## 28 September 2026: a shorter project page

- **Request (the engineer):** the project page was long and unstructured, the list of decisions wasn't useful, and
  revisions belong behind a floating button.
- **Change:** steps and status, the one card that needs the engineer (or the published revision on one line), then
  Packages | Files tabs; packages show amounts and a total. The decisions list is gone (the decision log keeps them),
  and the work API no longer returns it. Revisions open from a round button in the bottom corner (bottom-left in
  Arabic) into a panel with each revision's files, Open folder and Export; Escape or a click elsewhere closes it.
- **Checked** in the running app on El Far, English and Arabic; 123 service tests, 44 interface tests.

## 28 September 2026: UI/UX polish (branch `ui-polish`)

- **Request (the engineer):** run the ui-ux-polish skill: Stripe-level craft, desktop and narrow windows considered
  separately, passes until nothing big is left; later, "no truncation: fully responsive". Kept to the approved
  minimal look and the rules. On a branch, merged only if the engineer likes it.
- **Foundations:** one set of building blocks (`ui/src/app/ui.tsx`): buttons with hover, pressed, disabled and
  pending states, fields with a visible 3:1 edge and one focus ring, cards, pills, the page frame, alerts with Try
  again, skeletons, empty states, icons, amounts. One type scale, shadows that read in dark mode, short enter
  motion, reduced motion respected.
- **Responsive, nothing cut:** no text ends in "…" and no row scrolls sideways at any width down to 380px (the
  desktop window's new minimum). Names wrap; rows put details on a second line; the app tabs take their own row;
  items are a table where it fits and cards where it doesn't (measured); Excel's float noise shows to the cent with
  the exact value on hover. Checked at 375/380/480/640/1024/1280px in English and Arabic, light and dark.
- **Behaviour:** the language and theme apply before the first paint; buttons stay pending until the new state
  arrives; Packages | Files is a real tab list; the revisions panel takes and returns focus; focus moves to the next
  decision card; a package on the project page opens straight to its items; a confirm before a connection's key is
  deleted; amber only for "needs you".
- **Found and fixed on the way:** publishing failed when a revision's path passed Windows' 260 characters (a
  120-character package name is enough): revision files are now written and exported through extended paths. An
  unknown service failure read "({status})"; it now gives the status.
- **Checks:** 124 service tests, 49 interface tests, typecheck, Ruff, Clippy.

## 10 October 2026: QS Mind brand v2

- The "T" monogram is retired. Tawreed now carries the QS Mind sphere with its Steel face: the mark in the
  header (lines in the text colour, so ink on light and white on dark), the brand favicon, and app icons made from
  the full mark with the sphere's outline filled with Paper, as Qiyas does. Master files: `brand/tawreed/` in the
  QS Mind workspace.
- Founder's decisions: the header is the sphere and the name only; amber stays the one accent ("needs you") and
  Steel is for the mark only; Arabic headings use Thmanyah Sans with swash letters, so Thmanyah Serif Display is no
  longer loaded; English uses Kumbh Sans, the QS Mind site's typeface, in place of Figtree; the licence stays
  all rights reserved.
- App ID `com.tawreed.desktop` became `com.qsmind.tawreed` (before any release, so nothing moves for users). The
  installer's publisher is QS Mind.
- About was rebuilt: the mark at 64 px, the name, the tagline and the version, then three rows (made by QS Mind with a
  name itself the link to qsmind.app, the licence, the data folder) and the copyright line. No font credits in the
  interface (founder's decision). The link is opened by the service (`POST /about/website`), as the revision folders are.
- Kumbh Sans kerns "/." so tightly that the dot disappears; the data-folder path turns kerning off.
- No support email: support will be a form in the app that saves to the QS Mind database. Not built yet.
- Not done here: the repository is still private on GitHub; the launch-gaps items on logs and updates in About.

## 2 November 2026: sign in with QS Mind (branch `launch/qsmind-signin`)

- **Request (the founder, plan approved today):** required sign-in with the central QS Mind account before Home, the
  session in the service, the refresh token in the OS keychain, a 14-day offline lease then read-only, an Account
  line in Settings, and the AI keys moved from `auth.json` to the keychain. Spec:
  [2026-11-02-qsmind-sign-in.md](2026-11-02-qsmind-sign-in.md).
- **Built:** loopback PKCE sign-in in the system browser, a device code as the fallback (no deep link: it needs a
  plugin, single-instance hand-off and installer registration on three systems); hourly refresh in the background
  with rotating refresh tokens; past the lease, changes answer `403 read_only` and the AI steps wait. The protocol
  (`service/tawreed/account/qsmind.py`) imports nothing of Tawreed, for Quantix and Qiyas to copy.
- **Copy, founder's call:** the brief's "your BOQs never leave your computer" is not true once an AI service is
  connected, so the screen says the BOQs never go to QS Mind and go only to the chosen AI service after consent.
- **New dependency:** `keyring` 25.7 (MIT), with jaraco.classes, jaraco.context, jaraco.functools and more-itertools
  (MIT), and on Linux SecretStorage (BSD-3-Clause) and jeepney (MIT).
- **Waits on the account service:** registering Tawreed as a native client and putting its id in `CLIENT_ID`; a
  `plan` claim once plans exist. Until then sign-in says it is not available yet.
