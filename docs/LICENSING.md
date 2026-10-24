# Planner licensing

Copyright (c) 2026 Dieter Stassen. Planner has separate software, original-graphics,
branding and third-party terms. A public repository does not put any of these
works in the public domain.

## Software

Original Planner application source code, tests and build tools are licensed
under **GPL-3.0-only**. The unmodified full GPLv3 text is in [LICENSE](../LICENSE)
and the self-contained app's [COPYING](../planner-main/COPYING). This selection
does not grant a choice of later GPL versions. Third-party source retains its
own license.
The complete license text was copied verbatim from
[SPDX's GPL-3.0-only text](https://github.com/spdx/license-list-data/blob/main/text/GPL-3.0-only.txt).

The GPL permits commercial use, sale and distribution of compliant forks.
Distributed derivatives must satisfy its source and licensing requirements.
These permissions are independent of permission to use Planner's original
artwork or branding. Removing reserved artwork does not remove GPL obligations
from the code. See the [GNU GPLv3](https://www.gnu.org/licenses/gpl-3.0.html).

## Original graphics

[ASSET_LICENSE.txt](../planner-main/ASSET_LICENSE.txt) governs Dieter Stassen's
original furnishing graphics and original UI graphics. It permits using them
in Planner and sharing editable plans, embedded plan graphics, SVG/raster exports
and printed work, including paid or commercial work. Rendering transformations
such as scaling, recoloring, mirroring and conversion are permitted for those
purposes. Plans do not need visible attribution or attached license boilerplate.

It does not permit extracting or distributing the artwork as standalone assets,
stock graphics, icon packs or furnishing libraries. Copies can travel with
complete, unmodified official Planner source or binary packages. Modified
software distributions need replacement assets or separate written permission.
Do not infer ownership merely from a directory: Google icons and other
third-party material remain under their own terms, including any rights already
granted by their licensors. Resolve unclear provenance before assigning a license.

## Branding

[BRANDING_LICENSE.txt](../planner-main/BRANDING_LICENSE.txt) covers the original
Planner logo and application icon, including the current temporary artwork and
future designated replacements. They may travel with complete, unmodified
official Planner packages. They cannot be distributed separately or used on a
modified distribution without written permission. Forks must replace/remove
reserved branding and must not imply official endorsement.

These copyright permissions are separate from any trademark rights. The policy
does not claim that copyright in an image creates exclusive rights in a name.

## Documentation and third-party works

Original documentation and other original non-code content not otherwise
licensed retain copyright; they can be redistributed within complete, unmodified
official packages with notices intact. The guide itself has not been edited as
part of this licensing setup.

[LICENSES.txt](../planner-main/LICENSES.txt) identifies the software license and
existing PySide6/Qt, Google icon, font, UPNG and Pako notices. Retain all relevant
third-party license files. The new graphics policy cannot override Apache, OFL,
MIT, LGPL, or other permissions already granted by third-party copyright holders.
In particular, choosing GPL for Planner does not replace Qt's own terms.
All bundled fonts, including Drafting Small Caps (a modified Architects Daughter),
retain SIL OFL 1.1. Their complete notices and modification information are
included beside the fonts and displayed in the Licenses window. Planner's
reserved-graphics terms do not apply to these font files. See [fonts](resources/FONTS.md).

## Distribution and contributions

Include COPYING, ASSET_LICENSE.txt, BRANDING_LICENSE.txt, LICENSES.txt and the
third-party notices in application packages. The Licenses window displays them.
When distributing executables, provide the matching corresponding source and
build instructions in a way that satisfies GPL section 6. Publish a release tag
matching the executable; a generic link to the changing main branch does not
identify the exact corresponding source. See [release guidance](RELEASING.md).

Copyright owners can offer later releases or their own code under other terms,
but existing GPL grants remain available for previously released versions.
Outside contributors retain their copyright unless separately agreed. Their
GPL contributions do not automatically grant the project owner proprietary
relicensing rights. Agree additional contributor terms before accepting such
contributions if dual licensing is intended. See
[contribution guidance](../CONTRIBUTING.md) and the
[GNU relicensing explanation](https://www.gnu.org/licenses/gpl-faq.html#Consider).
