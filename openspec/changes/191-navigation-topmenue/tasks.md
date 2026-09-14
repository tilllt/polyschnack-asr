# Tasks — Change 191

- [ ] `view`-Zustand um `"benchmark"` und `"admin"` erweitern
- [ ] Top-Menü (Transkribieren · Settings · Benchmark · Admin) mit aktivem
      Zustand; alten Benchmark-Link und ⚙️-Knopf entfernen
- [ ] `<AdminPanel />` aus der Hauptansicht entfernen; eigene Ansicht „Admin"
      (nur bei `user.is_admin`)
- [ ] Login/Logout-Textknöpfe durch ein Symbol neben dem Usernamen ersetzen
      (`LogIn`/`LogOut`, `title` + `aria-label`)
- [ ] i18n: `benchmark`, `login`, `logout` in DE/EN/PT (falls fehlend)
- [ ] Vitest: Menü/aktiver Zustand, Admin-Sichtbarkeit, Symbol-Kontext
- [ ] `tsc --noEmit` + betroffene Vitest-Läufe grün
- [ ] Prod-Verifikation nach Deploy: Startseite ohne Admin-Kacheln, vier
      Menüpunkte, Symbol schaltet Login/Logout
