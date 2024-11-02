import json
from datetime import datetime, timedelta

def wczytaj_system():
    """Wczytuje dane systemu z pliku JSON."""
    try:
        with open('system.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            'uzytkownicy': {},
            'raporty': {},
            'dni_wolne': {
                'urlop': 'Urlop wypoczynkowy',
                'choroba': 'Zwolnienie lekarskie',
                'okolicznosciowy': 'Urlop okolicznościowy',
                'zadanie': 'Zadanie służbowe',
                'swieto': 'Święto'
            }
        }

def zapisz_system(system):
    """Zapisuje dane systemu do pliku JSON."""
    try:
        with open('system.json', 'w', encoding='utf-8') as f:
            json.dump(system, f, ensure_ascii=False, indent=4)
        
        # Weryfikacja zapisu
        with open('system.json', 'r', encoding='utf-8') as f:
            sprawdzenie = json.load(f)
            if sprawdzenie != system:
                print("UWAGA: Dane po zapisie różnią się od danych przed zapisem!")
                print("Różnice:", set(system.keys()) - set(sprawdzenie.keys()))
    except Exception as e:
        print(f"Błąd podczas zapisu systemu: {str(e)}")
        raise

def oblicz_czas_pracy(godzina_rozpoczecia, godzina_zakonczenia):
    """Oblicza czas pracy w godzinach."""
    if not godzina_rozpoczecia or not godzina_zakonczenia:
        return 0
    
    start = datetime.strptime(godzina_rozpoczecia, '%H:%M')
    koniec = datetime.strptime(godzina_zakonczenia, '%H:%M')
    
    roznica = koniec - start
    return round(roznica.total_seconds() / 3600, 2)  # Konwersja na godziny

def get_week_dates(selected_date):
    """Zwraca listę dat dla wybranego tygodnia."""
    date = datetime.strptime(selected_date, '%Y-%m-%d')
    monday = date - timedelta(days=date.weekday())
    return [(monday + timedelta(days=x)).strftime('%Y-%m-%d') for x in range(7)] 