# Tasks — Change 119 (CI-Fix: Globs + mirror-ghcr SHA-Guard)

## Done

- [x] Proposal: openspec/changes/119-ci-glob-fix/proposal.md
- [x] Alle changes-Globs `xyz/**` → `xyz/**/*` (GitLab-Doku: Verzeichnis +
      Subdirs braucht `**/*`; `webapp/frontend/**` matchte tiefe Pfade nicht)
- [x] mirror-ghcr: SHA-Tag nur bei existierendem Image (manifest inspect),
      sonst überspringen — `:latest` immer
- [x] OptionsPanel: useEffect-Deps + backends.length/streamingSupported
- [x] tsc + 312 Tests grün

## Verifikation

- [x] Push 2a1ebbb → Pipeline 4469: **5 Jobs statt 20** (test-frontend,
      test-webapp, build-webapp, 2 Mirrors) — keine ASR-Builds
- [x] Pipeline 4469 **success** in ~7 min: Glob-Fix wirkt, mirror-ghcr
      läuft mit SHA-Guard sauber durch
- [x] Ursache dokumentiert: Push-Pipeline 4467 (ee1131d) erkannte
      webapp-Änderungen nicht (`**`-Glob), manueller Trigger 4468 baute
      alles (changes ohne Push-Event = immer true)
