# Releases and version numbers

Planner currently displays **Alpha 0.1.0** in
[the About dialog](../planner-main/planner_app/ui/about.py). This licensing change
does not itself change that version or rebuild the executable.

## When to increment

Choose a new version when publishing a new release or build for users. Ordinary
commits and local testing do not each need a version increment. Several fixes
and features can be grouped into one release. Never replace an already published
version with different code while keeping the same version number.

Use major.minor.patch as a practical release convention:

| Change | Example |
| --- | --- |
| Compatible bug fixes | 0.1.0 to 0.1.1 |
| New features or substantial improvements | 0.1.x to 0.2.0 |
| Breaking compatibility during initial development | Advance the 0.x minor version and explain the break |
| First supported stable release | 1.0.0 |
| Breaking supported compatibility after 1.0 | 1.x.y to 2.0.0 |

Reset patch to zero when increasing minor; reset minor and patch when increasing
major. After 1.0, compatible features advance minor and compatible fixes advance
patch. Compatibility includes documented CLI behavior and integrations, and
requires considering saved plans, furnishing definitions and user workflows.
A visual adjustment alone is not automatically a major release.

Optional prerelease identifiers distinguish test builds, for example
0.2.0-alpha.1, 0.2.0-alpha.2, 0.2.0-beta.1, then 0.2.0. The app can display a
friendlier label, but the release/tag should identify the exact version. A Git
tag can be named v0.2.0-alpha.1. The current pre-1.0 designation already indicates
initial development; there is no need to rename an existing release retroactively.

This is a release policy informed by [Semantic Versioning](https://semver.org/),
whose strict rules concern a declared public API. Planner's 0.x releases do not
promise a stable API. Keep the project-file format's integer version separate
from the application's release number; a normal app release need not change it.

## Before publishing

1. Choose the release number and update the About dialog's version label and its
   focused check. Record the release's changes in the release notes.
2. Run the relevant checks and the complete CI suite before publishing.
3. Create an immutable Git tag for the exact reviewed source revision.
4. Build the executable from that revision when a binary release is intended,
   following [Windows build instructions](WINDOWS_BUILD.md). Do not rebuild for
   every development edit.
5. Include the matching corresponding source and required build materials with
   the binary release using a GPL-compliant distribution method. GitHub's source
   archive for the matching tag can supply source if it contains all required
   materials. Include extra required materials if it does not.
6. Keep the software, original-graphics, branding and third-party notices in
   source and binary packages. Check that the Licenses window can display them.

The policy applies to future releases; it does not rewrite earlier releases or
withdraw permissions already granted for them. See [licensing](LICENSING.md).
