# Tawreed specification

## What Tawreed is

Tawreed turns construction bills of quantities into procurement packages. An engineer adds one or more BOQs for a
project; Tawreed reads them, designs a package structure that fits the project and the supplier market, places
every BOQ item in exactly one package, and publishes workbooks the engineer can send to specialist suppliers and
subcontractors for pricing. It is a fixed workflow, not a conversation: the AI does the reading, planning and placing
as steps, and the engineer approves at every gate.

Tawreed never changes what the BOQ says. Item codes, descriptions, units, quantities, rates, amounts and comments
reach the outputs exactly as they are in the source.

## Who uses it

Quantity surveyors, estimators and procurement engineers working on their own computer, on BOQs in English, Arabic
or both. They know construction; they should not need to know anything about AI models.

## The work

1. **Project.** The engineer creates a project and adds BOQ files. A project can hold several BOQs.
2. **Reading.** Tawreed keeps an unchanged copy of each file and reads it. The AI works out each file's layout
   (which sheet, which header row, which column is the quantity, where a PDF's columns fall); Tawreed extracts the
   exact values into the project's item ledger, each item linked to its cell or page. Scanned pages are read by the
   AI from the page image; those rows are marked "read from image — verify" and shown beside the page.
3. **Overlap.** When a new file overlaps the project's existing sources, the engineer decides whether it is an
   addition, a replacement or a revision. *(Gate)*
4. **Package plan.** The AI proposes the packages: a name, the scope each covers and why. It balances clear
   specialist scope, how suppliers and subcontractors actually trade, practical package size and no needless
   fragmentation. It uses the project's rules and any rules the engineer promoted to all projects. The engineer
   approves the plan, edits it first (rename, scope, remove, merge, add), or has it proposed again with a note.
   *(Gate)*
5. **Assignment.** The AI places every item in one package. Items it cannot place with confidence are shown
   with the candidate packages and its reasoning; the engineer picks, and chooses whether the choice applies to
   this item, the project (default) or all future projects. *(Gate)*
6. **Checks.** Tawreed verifies that every active item appears exactly once and that package totals reconcile with
   the source totals.
7. **Publish.** When every item is placed, Tawreed shows what the revision holds, computed, and the engineer
   approves. *(Gate)* Tawreed writes the whole revision at once: either all of it appears, or none of it does. The
   same work can be published again, for instance once with rates and once for suppliers to price.

The steps run on their own from the dropped BOQ to each gate, and the gates always stop for the engineer. There is
no conversation. The engineer corrects the work in two ways, both through the same checked operations:

- **Directly:** move items between packages, rename, merge, remove or add packages, set a sheet's columns, or set a
  page aside. The AI leaves the engineer's own layouts and placements as they are.
- **Run a step again, with an optional note for the AI:** read a file or a page again, or place a package's items
  (or everything the AI placed) again. A page read again the same way keeps its placements.

A status line says what runs (with Stop) or why the work paused (with Continue): an AI failure, a step that got
nowhere twice, or a declined consent.

## Inputs

Excel (`.xlsx`, `.xlsm`, `.xls`), CSV (including Arabic Windows-1256), ODS, searchable PDF, scanned PDF and page
images. Any layout: there is no required template.

## Outputs of a revision

- **Master workbook:** cover, package index with item counts and totals, one sheet per package.
- **Package workbooks:** one standalone workbook per package, ready to send. At publishing the engineer chooses
  whether they show rates and amounts; without them the rates are left for suppliers to fill, and an item the source
  prices but leaves out of its amounts (a rate with no amount) stays out of the package total.
- **Simple formulas:** an amount is `=Qty*Rate` wherever that gives the source's own amount (otherwise the source's
  figure stays), package totals are `=SUM(...)`, the package index refers to each package's total and the cover adds
  them up.
- **Decision log:** what the AI proposed and what the engineer decided, with reasons and rules applied.
- **Coverage check:** every source item once, and source totals against output totals.
- **For review:** every printed sheet is headed "For review". The cover and each package sheet state Tawreed's
  limits in one line, and the cover lists the assumptions behind the figures.

Revisions are numbered `Rev 00`, `Rev 01`, … and kept under the project in `~/.tawreed`, with Open folder and
Export to… actions. Arabic projects get right-to-left sheets.

## AI

- API keys for Anthropic, OpenAI, Google, xAI and one OpenAI-compatible endpoint.
- A ChatGPT subscription, only through the official Codex client. Tawreed never reads or copies its sign-in
  tokens.
- A model can be used only after Tawreed checks that it calls tools correctly. The same check records whether it
  can read images, which scanned pages need.
- The first time a project's content would go to a connection, Tawreed shows what is sent and where, and asks.
  The answer is remembered for that project and connection.
- Without a working connection, projects, sources and past revisions stay open and files can still be read;
  the AI steps wait for one.
- No spending controls in v1. Each run of a step has a step limit, and the work pauses when a step gets nowhere
  twice.

## Interface

Tawreed is a tool, not a workspace. One window with four tabs: **Home**, **History**, **Settings** and **About**.

- **Home** starts as a drop zone ("Drop BOQ files here", or Choose files), Tawreed's limits of use in one line,
  and the recent projects below it.
  Dropping files starts the work; dropping more files onto a running project adds them to it.
- An open project shows, in this order: its name, a five-step line (Read · Plan · Place · Check · Publish) and a
  status line; the one thing waiting for the engineer (a decision card), or else the published revision on one line
  with Open folder, Export to… and Publish again; then two tabs, **Packages** (each package's items and amount, and
  the total, with View and edit) and **Files** (each file shows how each of its pages was read). What the engineer
  decided is not listed on the page; it is in each revision's decision log.
- A round button in the page's bottom corner shows how many revisions there are and opens them: each with its
  files, Open folder and Export to….
- **History** lists past projects and their revisions; opening one returns to Home for that project.
- **Settings**: the QS Mind account (who is signed in, the plan, Sign out), language, theme, the AI Tawreed works
  with, connections, and rules that apply to all projects.
- **Sign-in** with QS Mind comes before Home, in the system browser or with a code. Only the account goes to QS Mind;
  BOQs never do. Tawreed works offline for 14 days after the last refresh, then is read-only until it reaches QS Mind
  again, and loses nothing. See `docs/2026-11-02-qsmind-sign-in.md`.
- **About**: version, limits of use, data folder, logs, updates and licences.

Minimal and calm: white (or near-black in dark mode), hairlines, black primary buttons, and one amber accent that
means "needs you". No sidebars, dashboards or decoration.

## Language and platform

English and Arabic interface with full right-to-left layout; the AI writes package names, scopes and reasons in
the interface language. English
text uses Kumbh Sans and Arabic text uses Thmanyah Sans, with its swash letters on Arabic headings: light
headings, regular body text. Light and dark themes, following the system. A desktop app on
Windows first.

## Data

Everything Tawreed manages lives in `~/.tawreed`: AI connections in `connections.json` and who is signed in to QS
Mind in `account.json` (readable only by the user), settings in `settings.json`, projects in the database, source copies
and revisions under each project. Supplied files are never changed. The AI keys and the QS Mind refresh token are
in the operating system's keychain, never shown in full or logged.

## Not in v1

Material takeoff, sending enquiries, bid comparison, other operating
systems, spending controls.

## Done when

- A synthetic multi-BOQ project in English and in Arabic goes through every gate and publishes a revision whose
  coverage check passes.
- A real BOQ (`BoQ - Package 04 (Combined) - R1`, kept private and never committed) publishes with full coverage and
  reconciled totals, and the engineer spot-checks a sample.
- Every provider type passes its connection check.
- Service tests, interface tests, typecheck and lint pass in CI, and a Windows installer is on GitHub Releases.
