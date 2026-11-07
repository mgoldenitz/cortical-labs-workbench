# License options for this project's original code

Decision (2026-11-07): Michael chose the MIT License for the project's original code; see the root `LICENSE` file and [licensing.md](licensing.md). The rest of this page is the comparison as it stood before the decision. It is not a recommendation and not legal advice. It covers only the code written for this project (`src/`, `tests/`, `tools/`, `docs/`, `discovery/`). Third-party material, including cl-sdk under CC BY-NC 4.0, keeps its own terms whatever is chosen here; see [licensing.md](licensing.md).

| Option | What others may do with this project's code | Main obligations on them | Points specific to this project |
| --- | --- | --- | --- |
| No license (current state) | Read it, and fork it on GitHub under GitHub's terms if the repo is public; no permission to reuse, modify or redistribute | n/a | Default copyright applies. Fine while the repo is private or a portfolio piece. |
| MIT | Use, modify, redistribute, including commercially | Keep the copyright and license notice | Short and widely recognised. No explicit patent grant. |
| Apache-2.0 | Same as MIT | Keep notices, state significant changes, pass on any NOTICE file | Explicit patent license and patent-termination clause. Longer text. |
| BSD-3-Clause | Same as MIT | Keep notices; may not use the author's name to endorse derived products | Close to MIT with a no-endorsement clause. |
| GPL-3.0 | Use and modify; redistributed versions must be GPL-3.0 with source | Share source of distributed derivatives under the same license | The code runs against cl-sdk, which carries a non-commercial restriction; whether distributing the combination fits GPL-3.0's no-further-restrictions rule is a question for legal review. |
| CC BY-NC 4.0 (same as cl-sdk) | Use and adapt for non-commercial purposes | Attribution; no commercial use | Matches the SDK's terms. Creative Commons advises against using its licenses for software, because they do not address source code or patents. |

Things that hold whichever option is picked:

- A permissive license on this code does not make cl-sdk usable commercially. Anyone running the tool still installs cl-sdk under CC BY-NC 4.0.
- The license can be added later in one commit (a `LICENSE` file plus a `license` field in `pyproject.toml`). Nothing in the code depends on it.
- If anyone else contributes code before a license is chosen, their permission would be needed to license their part.
