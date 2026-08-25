# Tasks — Change 121 (transcribe überschreibt Upload-Settings nicht mehr)

## Done

- [x] Proposal: openspec/changes/121-transcribe-keeps-upload-settings/proposal.md
- [x] Roter Test: Upload mit VAD/Diarize → transcribe ohne Felder → Settings bleiben
      (2 failed, 1 passed — stiller Fail belegt)
- [x] Fix in transcribe_ep: Optional-Parameter, None = Run-Wert behalten;
      Modell-Defaults für neue Runs; Form-Objekt-Guards für direkte Aufrufe
- [x] pytest tests/test_transcribe_keeps_upload_settings.py grün (3/3)
- [x] Betroffene Suiten grün: diarize_params, vad_modes, llm_endpoint_use,
      realign_routes, realign (41/41)
- [x] Live: Upload mit VAD → transcribe ohne Parameter → Run behält VAD

## Verifikation

- [ ] Backend-Gesamtsuite tests/ grün (läuft)
- [ ] Push main → CI success
- [ ] Prod-Deploy durch User
