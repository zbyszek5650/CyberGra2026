# 🛡️ CyberGra v4 — Silnik Symulacji Kryzysowej

## Opis
Interaktywna gra symulacyjna dla zespołów, modelująca scenariusze kryzysów cyberbezpieczeństwa w sektorze bankowym i innych branżach krytycznych. Silnik oparty na Streamlit, działający bez bazy danych (stan w pamięci z `@st.cache_resource`).

## Cechy
- **5 Scenariuszy × 6 Podetapów** = 30 rund decyzyjnych
- **System 2 żyć** — eliminacja po utracie obu, z możliwością reaktywacji przez trenera
- **4 metryki KPI**: Płynność, Cyberbezpieczeństwo, Regulacje, Reputacja
- **Notowania akcji** w czasie rzeczywistym (symulowane)
- **Nowoczesny UI** z efektem Glassmorphism i powiększoną typografią
- **Panel studenta** z widgetem pulsujących żyć i podglądem rankingu na żywo
- **Panel administratora** z pełną kontrolą rund, przerwami między scenariuszami i ręcznym przywracaniem żyć

## Scenariusze
| # | Scenariusz | Opis |
|---|-----------|------|
| 1 | Atak na Sektor Bankowy | SWIFT / Ransomware / Panic Run / DDoS / Kontrola UODO / Zero Trust |
| 2 | Kryzys Energetyczny | SCADA/ICS / Blackout / Rynek energii / Wyciek danych / URE / Resilience |
| 3 | Wojna Informacyjna | Deepfake / Zaufanie publiczne / Social media / Źródła info / Kontratak / Odporność |
| 4 | Atak na Łańcuch Dostaw | Kompromitacja dostawcy / Backdoor / Eskalacja / Containment / Audyt / Nowa architektura |
| 5 | Infrastruktura Rządowa | Spear phishing / e-Gov / Wyciek danych / Wybory / Eskalacja międzynarodowa / Cyber resilience |

```

## Struktura
```
cyber_crisis_v4/
├── app.py                          # Główna aplikacja Streamlit
├── requirements.txt                # Zależności Python
├── README.md                       # Ten plik
└── config/
    └── bank_cyber_crisis.yaml      # Konfiguracja 5 scenariuszy × 6 rund
```

## Logowanie
- **Zespoły**: Nazwa zespołu + 4-cyfrowy PIN (rejestracja przez admina)
- **Administrator**: PIN domyślny `admin2024` (zmień w ustawieniach)

## Licencja
Projekt edukacyjny — do użytku wewnętrznego.


## Uruchomienie

```bash
cd cyber_crisis_v4
pip install -r requirements.txt
streamlit run app.py



python -m streamlit run app.py         admin2024