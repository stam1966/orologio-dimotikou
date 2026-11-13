# Code signing policy / Πολιτική ψηφιακής υπογραφής

**Ωρολόγιο Σχολείου** — Ιδέα και σχεδιασμός: Σταμάτης Κοκολόγος, εκπαιδευτικός ΠΕ70, 22ο Δημοτικό Σχολείο Λαμίας.

## English

Free code signing for Windows releases is provided by [SignPath.io](https://about.signpath.io), certificate by [SignPath Foundation](https://signpath.org).
*(Status: application submitted — until approval, releases are not yet signed.)*

**What is signed:** the Windows installers published on [GitHub Releases](https://github.com/stam1966/orologio-sxoleiou/releases) (Orologio_Sxoleiou_Setup*.exe, Sxolikes_Efarmoges_Setup*.exe). They are built from this repository by GitHub Actions (`.github/workflows/build.yml`); no binaries are built or signed on personal computers. Third-party upstream binaries are not signed with this certificate.

**Team roles**
| Role | Members |
|---|---|
| Committers and reviewers | [stam1966](https://github.com/stam1966) (Stamatis Kokologos, owner) |
| Approvers | [stam1966](https://github.com/stam1966) (Stamatis Kokologos, owner) |

All team members use multi-factor authentication for GitHub and SignPath. Every release requires manual approval before signing. Changes from non-members (pull requests) are reviewed before merging.

**Privacy policy:** This program will not transfer any information to other networked systems unless specifically requested by the user or the person installing or operating it. Exceptions, all initiated or enabled by the user: (1) checking for new versions on GitHub (can be disabled in the settings; no user data is sent); (2) the optional AI assistant, which sends the request to the AI provider the user selects and configures with their own key — teacher names are replaced by codes before sending, by default.

**Uninstallation:** the installers register a normal Windows uninstaller (Settings → Apps). User data is kept in the data folder and can be deleted manually.

**License:** GNU General Public License v3.0 ([LICENSE](LICENSE)). Third-party components: embedded CPython 3.12 (PSF License), Google OR-Tools (Apache-2.0), numpy/pandas/protobuf/absl-py and related libraries (BSD/Apache-2.0/MIT), openpyxl and et_xmlfile (MIT); Microsoft Visual C++ runtime DLLs (system libraries). Their licenses are included in the installed files.

## Ελληνικά

Η δωρεάν ψηφιακή υπογραφή των εκδόσεων για Windows παρέχεται από το SignPath.io, με πιστοποιητικό του SignPath Foundation (μόλις εγκριθεί η αίτηση). Υπογράφονται μόνο τα αρχεία εγκατάστασης των GitHub Releases, που χτίζονται αυτόματα από αυτό το αποθετήριο στο GitHub Actions. Κάθε έκδοση υπογράφεται μόνο μετά από χειροκίνητη έγκριση του δημιουργού.

**Ιδιωτικότητα:** η εφαρμογή δεν στέλνει πληροφορίες σε άλλα συστήματα, εκτός αν το ζητήσει ο χρήστης. Τα δεδομένα του σχολείου μένουν στον υπολογιστή ή στον κοινό φάκελο του σχολείου.
