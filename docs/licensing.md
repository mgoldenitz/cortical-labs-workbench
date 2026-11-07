# Licensing notes

This is a factual record for review, not legal advice. Installing cl-sdk with pip does not by itself establish that a given use complies with its license; whether a use is allowed depends on what is done with the software and its outputs. Anything that could count as commercial use should go to Cortical Labs for permission or to a lawyer before it happens.

## cl-sdk (third party)

- Pinned version: cl-sdk 1.0.0 from PyPI. Source repository commit `a9a2f9c0cefaa032075d7cd7ccbbc4b037ba1991` (tag v1.0.0).
- License file: Creative Commons Attribution-NonCommercial 4.0 International Public License (CC BY-NC 4.0), legal code text. The `LICENSE` in the repository at that commit and the `LICENSE` inside the installed wheel are identical, SHA-256 `55f908cdcef66a0c61a725b8ee4905e9f8011da94385e593a636ead53740e4fc`. Canonical text: <https://creativecommons.org/licenses/by-nc/4.0/legalcode>.
- Package metadata is not fully consistent: `License: CC BY-NC 4.0` alongside the classifier `License :: Other/Proprietary License`. The license file is taken as the operative text here; this inconsistency is worth raising with Cortical Labs if it matters.
- Licensor: the package lists "Cortical Labs Pte Ltd" (info@corticallabs.com) as author. The license file itself contains no copyright line.
- NonCommercial is defined in section 1(i) of the license as "not primarily intended for or directed towards commercial advantage or monetary compensation".
- Attribution (section 3(a)) applies when you Share the Licensed Material, including in modified form: keep creator identification, copyright notice, a notice referring to the license and to the warranty disclaimer, a link to the material where practicable, indicate modifications, and include or link the license text.

## What this repository contains

| Material | Origin | License status |
| --- | --- | --- |
| `src/workbench/`, `tests/`, `tools/`, `docs/` | Written for this project | No license chosen yet (see below) |
| `discovery/*.py` | Written for this project; `smoke.py` reproduces a few lines of example calls from cl-api-doc notebooks CL-00, CL-01 and CL-02 | cl-api-doc at commit `a6726472...` has no license file, so reuse terms for its notebook code are not stated. Flagged for review; the copied calls are short API examples. |
| cl-sdk source code | Not included. Installed from PyPI at setup time | CC BY-NC 4.0 |
| Electrode layout values | Not copied. Read at run time from the private module `cl.analysis._metrics._mea_layout` (`src/workbench/layout.py`) | Stays inside the installed cl-sdk |
| Other Python dependencies | Installed from PyPI | See [third-party-licenses.md](third-party-licenses.md). Two packages declare no license in their metadata (`dotenv` 0.9.9, a shim that installs `python-dotenv`; `ptyprocess` declares only an ISC classifier). |

Run outputs (`runs/`, `*.h5`) are ignored by git. Whether simulator output files are covered by the cl-sdk license is not addressed in the license text in a way this note can settle; treat publishing them as a question for review.

## Situations that change the analysis

- Publishing this repository: shares our code, not cl-sdk. The README tells readers to install cl-sdk themselves and states its license.
- Building a container image or any bundle that includes cl-sdk (the proposed AWS execution stage): that is Sharing the Licensed Material. Attribution duties apply, and the image must not be used or offered commercially without permission. This is called out again in [aws-proposal.md](aws-proposal.md).
- Paid work, a product, a paid service, or use inside a company: flag for permission or legal review first.

## This project's own code

No license has been chosen for the original code in this repository, so default copyright applies. The options are listed separately in [project-license-options.md](project-license-options.md); no choice is made here.
