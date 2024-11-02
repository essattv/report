import os
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from datetime import datetime, timedelta
from system import SystemRaportowania
import tempfile
import pdfkit

app = Flask(__name__)
# Użyj zmiennej środowiskowej dla secret_key
app.secret_key = os.environ.get('SECRET_KEY', 'tajny_klucz_aplikacji')

# Konfiguracja wkhtmltopdf dla różnych środowisk
if os.environ.get('RENDER'):
    # Ścieżka na Render
    WKHTMLTOPDF_PATH = '/usr/bin/wkhtmltopdf'
else:
    # Ścieżka lokalna (Windows)
    WKHTMLTOPDF_PATH = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'

config = pdfkit.configuration(wkhtmltopdf=WKHTMLTOPDF_PATH)

# Utwórz instancję systemu
system = SystemRaportowania()

@app.context_processor
def inject_system():
    return dict(system=system)

# Dodaj dekorator wymaga_zalogowania
def wymaga_zalogowania(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'uzytkownik' not in session:
            return redirect(url_for('logowanie'))
        return f(*args, **kwargs)
    return decorated_function

# Dodaj funkcję sprawdzającą czy użytkownik jest adminem
def czy_admin(login):
    return system.uzytkownicy.get(login, {}).get('admin', False)

@app.route('/')
def index():
    if 'uzytkownik' not in session:
        return redirect(url_for('logowanie'))
    return render_template('index.html')

@app.route('/logowanie', methods=['GET', 'POST'])
def logowanie():
    if request.method == 'POST':
        login = request.form['login']
        haslo = request.form['haslo']
        
        if login in system.uzytkownicy and system.uzytkownicy[login]['haslo'] == haslo:
            session['uzytkownik'] = login
            session['admin'] = system.uzytkownicy[login]['admin']
            session['wyswietlana_nazwa'] = system.uzytkownicy[login].get('wyswietlana_nazwa', login)
            flash('Zalogowano pomyślnie!', 'success')
            return redirect(url_for('index'))
        flash('Nieprawidłowy login lub hasło!', 'error')
    
    return render_template('logowanie.html')

@app.route('/rejestracja', methods=['GET', 'POST'])
def rejestracja():
    if request.method == 'POST':
        login = request.form['login']
        haslo = request.form['haslo']
        imie = request.form['imie']
        nazwisko = request.form['nazwisko']
        czy_admin = 'admin' in request.form
        
        if login in system.uzytkownicy:
            flash('Użytkownik już istnieje!', 'error')
        else:
            system.uzytkownicy[login] = {
                'haslo': haslo,
                'admin': czy_admin,
                'imie': imie,
                'nazwisko': nazwisko,
                'wyswietlana_nazwa': f"{imie} {nazwisko}"
            }
            system.raporty[login] = []
            system.zapisz_dane()
            flash('Konto zostało utworzone!', 'success')
            return redirect(url_for('logowanie'))
    
    return render_template('rejestracja.html')

def oblicz_czas_pracy(godzina_rozpoczecia: str, godzina_zakonczenia: str) -> float:
    """Oblicza czas pracy w godzinach"""
    start = datetime.strptime(godzina_rozpoczecia, '%H:%M')
    koniec = datetime.strptime(godzina_zakonczenia, '%H:%M')
    
    if koniec < start:  # Praca do następnego dnia
        koniec += timedelta(days=1)
    
    roznica = koniec - start
    return round(roznica.total_seconds() / 3600, 2)  # Konwersja na godziny

@app.route('/dodaj_raport', methods=['POST'])
@wymaga_zalogowania
def dodaj_raport():
    data = request.form.get('data')
    
    # Sprawdź czy data jest poprawna
    if not data:
        flash('Błąd: nie podano daty!', 'danger')
        return redirect(url_for('moje_raporty'))
    
    try:
        # Sprawdź format daty
        datetime.strptime(data, '%Y-%m-%d')
    except ValueError:
        flash('Błąd: nieprawidłowy format daty!', 'danger')
        return redirect(url_for('moje_raporty'))

    is_dzien_wolny = request.form.get('is_dzien_wolny') == 'on'
    dzien_wolny = request.form.get('dzien_wolny')
    
    nowy_raport = {
        'data': data
    }
    
    if is_dzien_wolny and dzien_wolny:
        nowy_raport['dzien_wolny'] = dzien_wolny
    else:
        nowy_raport.update({
            'godzina_rozpoczecia': request.form.get('godzina_rozpoczecia'),
            'godzina_zakonczenia': request.form.get('godzina_zakonczenia'),
            'godzina_rozpoczecia_nadgodzin': request.form.get('godzina_rozpoczecia_nadgodzin'),
            'godzina_zakonczenia_nadgodzin': request.form.get('godzina_zakonczenia_nadgodzin'),
            'godzina_rozpoczecia_zdalnej': request.form.get('godzina_rozpoczecia_zdalnej'),
            'godzina_zakonczenia_zdalnej': request.form.get('godzina_zakonczenia_zdalnej')
        })
    
    # Sprawdź czy raport na tę datę już istnieje
    raporty_uzytkownika = system.raporty.get(session['uzytkownik'], [])
    for i, raport in enumerate(raporty_uzytkownika):
        if raport['data'] == data:
            flash('Raport na ten dzień już istnieje!', 'error')
            return redirect(url_for('moje_raporty'))
    
    # Dodaj nowy raport
    if session['uzytkownik'] not in system.raporty:
        system.raporty[session['uzytkownik']] = []
    
    system.raporty[session['uzytkownik']].append(nowy_raport)
    system.zapisz_dane()
    
    flash('Raport został dodany!', 'success')
    return redirect(url_for('moje_raporty'))

@app.route('/moje_raporty')
def moje_raporty():
    # Pobierz bieżącą datę
    today = datetime.now().date()
    
    # Znajdź poniedziałek bieżącego tygodnia
    current_week_start = today - timedelta(days=today.weekday())
    
    # Zawsze używaj bieżącego tygodnia jako domyślnego, ignorując parametr week z URL
    selected_week = current_week_start.strftime('%Y-%m-%d')
    
    # Generowanie listy tygodni
    weeks = []
    for i in range(-10, 11):
        week_start = current_week_start + timedelta(weeks=i)
        week_end = week_start + timedelta(days=6)
        is_current = week_start == current_week_start
        
        weeks.append({
            'dates': [d.strftime('%Y-%m-%d') for d in [week_start + timedelta(days=x) for x in range(7)]],
            'start': week_start.strftime('%Y-%m-%d'),
            'end': week_end.strftime('%Y-%m-%d'),
            'is_current': is_current
        })
    
    # Sortuj tygodnie od najnowszego do najstarszego
    weeks.sort(key=lambda x: x['start'], reverse=True)
    
    # Generuj daty dla wybranego tygodnia (zawsze bieżący)
    week_dates = [(current_week_start + timedelta(days=x)).strftime('%Y-%m-%d') for x in range(7)]
    
    # Słownik z opisami dni wolnych
    dni_wolne = {
        'DW': 'Dzień wolny',
        'CH': 'Chorobowe',
        'WŚ': 'Wolne świąteczne',
        'NŻ': 'Urlop na żądanie',
        True: 'Dzień wolny',  # dla przypadku gdy dzien_wolny jest boolean
        False: '',  # dla przypadku gdy dzien_wolny jest boolean
        None: ''
    }
    
    # Pobierz wszystkie raporty pracownika
    raporty = system.pobierz_raporty_pracownika(session['uzytkownik'])
    
    # Zbierz wszystkie unikalne daty raportów
    daty_raportow = sorted(set(raport['data'] for raport in raporty))
    
    if not daty_raportow:
        # Jeśli nie ma raportów, pokaż bieżący tydzień
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        week_dates = [(monday + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]
        weeks = [{
            'start': monday.strftime('%d.%m.%Y'),
            'end': (monday + timedelta(days=6)).strftime('%d.%m.%Y'),
            'dates': week_dates,
            'is_current': True
        }]
    else:
        # Grupuj daty raportów w tygodnie
        weeks = []
        for data_str in daty_raportow:
            data = datetime.strptime(data_str, '%Y-%m-%d').date()
            monday = data - timedelta(days=data.weekday())
            week_end = monday + timedelta(days=6)
            
            # Sprawdź czy ten tydzień już istnieje
            week_exists = False
            for week in weeks:
                week_start = datetime.strptime(week['dates'][0], '%Y-%m-%d').date()
                if monday == week_start:
                    week_exists = True
                    break
            
            if not week_exists:
                week_dates = [(monday + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]
                weeks.append({
                    'start': monday.strftime('%d.%m.%Y'),
                    'end': week_end.strftime('%d.%m.%Y'),
                    'dates': week_dates,
                    'is_current': monday == (date.today() - timedelta(days=date.today().weekday()))
                })
        
        # Sortuj tygodnie od najnowszego
        weeks.sort(key=lambda x: datetime.strptime(x['dates'][0], '%Y-%m-%d'), reverse=True)
    
    # Pobierz aktualnie wybrany tydzień
    selected_week = request.args.get('week', weeks[0]['dates'][0] if weeks else None)
    if selected_week:
        selected_date = datetime.strptime(selected_week, '%Y-%m-%d').date()
        selected_monday = selected_date - timedelta(days=selected_date.weekday())
        week_dates = [(selected_monday + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]
    
    # Przekształć raporty na słownik z datami jako kluczami
    reports_by_date = {raport['data']: raport for raport in raporty}
    
    return render_template('moje_raporty.html',
                         weeks=weeks,
                         selected_week=selected_week,
                         current_week_start=current_week_start.strftime('%Y-%m-%d'),
                         current_week_end=(current_week_start + timedelta(days=6)).strftime('%Y-%m-%d'),
                         week_dates=week_dates,
                         reports_by_date=reports_by_date,
                         system=system,
                         dni_wolne=DNI_WOLNE)

@app.route('/raporty_pracownika/<login>')
@wymaga_zalogowania
def raporty_pracownika(login):
    if not czy_admin(session['uzytkownik']):
        return redirect(url_for('index'))

    # Pobierz wszystkie raporty pracownika
    raporty = system.pobierz_raporty_pracownika(login)
    
    # Zbierz wszystkie unikalne daty raportów
    daty_raportow = sorted(set(raport['data'] for raport in raporty))
    
    if not daty_raportow:
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        week_dates = [(monday + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]
        weeks = [{
            'start': monday.strftime('%d.%m.%Y'),
            'end': (monday + timedelta(days=6)).strftime('%d.%m.%Y'),
            'dates': week_dates,
            'is_current': True
        }]
    else:
        # Grupuj daty raportów w tygodnie
        weeks = []
        for data_str in daty_raportow:
            data = datetime.strptime(data_str, '%Y-%m-%d').date()
            monday = data - timedelta(days=data.weekday())
            week_end = monday + timedelta(days=6)
            
            # Sprawdź czy ten tydzień już istnieje
            week_exists = False
            for week in weeks:
                week_start = datetime.strptime(week['dates'][0], '%Y-%m-%d').date()
                if monday == week_start:
                    week_exists = True
                    break
            
            if not week_exists:
                week_dates = [(monday + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]
                weeks.append({
                    'start': monday.strftime('%d.%m.%Y'),
                    'end': week_end.strftime('%d.%m.%Y'),
                    'dates': week_dates,
                    'is_current': monday == (date.today() - timedelta(days=date.today().weekday()))
                })
        
        # Sortuj tygodnie od najnowszego
        weeks.sort(key=lambda x: datetime.strptime(x['dates'][0], '%Y-%m-%d'), reverse=True)

    # Pobierz aktualnie wybrany tydzień
    selected_week = request.args.get('week', weeks[0]['dates'][0] if weeks else None)
    if selected_week:
        selected_date = datetime.strptime(selected_week, '%Y-%m-%d').date()
        selected_monday = selected_date - timedelta(days=selected_date.weekday())
        week_dates = [(selected_monday + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]

    # Przekształć raporty na słownik z datami jako kluczami
    reports_by_date = {raport['data']: raport for raport in raporty}

    return render_template('raporty_pracownika.html',
                         login=login,
                         weeks=weeks,
                         week_dates=week_dates,
                         reports_by_date=reports_by_date,
                         selected_week=selected_week,
                         dni_wolne=DNI_WOLNE,  # Używamy istniejącego słownika
                         system=system)

@app.route('/lista_pracownikow')
def lista_pracownikow():
    if 'uzytkownik' not in session or not session['admin']:
        flash('Brak uprawnień!', 'error')
        return redirect(url_for('index'))
    
    return render_template('lista_pracownikow.html', uzytkownicy=system.uzytkownicy)

@app.route('/wyloguj')
def wyloguj():
    session.clear()
    return redirect(url_for('logowanie'))

@app.route('/usun_raport/<string:data>', methods=['POST'])
def usun_raport(data):
    if 'uzytkownik' not in session:
        return redirect(url_for('logowanie'))
    
    raporty_uzytkownika = system.raporty.get(session['uzytkownik'], [])
    
    # Znajdź i usuń raport
    for i, raport in enumerate(raporty_uzytkownika):
        if raport['data'] == data:
            del system.raporty[session['uzytkownik']][i]
            system.zapisz_dane()
            flash('Raport został usunięty!', 'success')
            break
    
    return redirect(url_for('moje_raporty'))

@app.route('/sprawdz_raport/<login>/<data>')
def sprawdz_raport(login, data):
    if 'uzytkownik' not in session or not session['admin']:
        return jsonify({'success': False, 'message': 'Brak uprawnień!'})
    
    raporty_uzytkownika = system.raporty.get(login, [])
    for raport in raporty_uzytkownika:
        if raport['data'] == data:
            if raport.get('dzien_wolny'):
                return jsonify({'success': False, 'message': 'Nie można dodać nadgodzin do dnia wolnego!'})
            return jsonify({'success': True})
    
    return jsonify({'success': False, 'message': 'Brak raportu dla wybranego dnia!'})

@app.route('/dodaj_nadgodziny/<login>/<data>', methods=['POST'])
def dodaj_nadgodziny(login, data):
    if 'uzytkownik' not in session or not session['admin']:
        flash('Brak uprawnień!', 'error')
        return redirect(url_for('index'))
    
    # Sprawdź czy raport istnieje
    raporty_uzytkownika = system.raporty.get(login, [])
    raport_istnieje = False
    
    for raport in raporty_uzytkownika:
        if raport['data'] == data:
            raport_istnieje = True
            if raport.get('dzien_wolny'):
                flash('Nie można dodać nadgodzin do dnia wolnego!', 'error')
                return redirect(url_for('raporty_pracownika', login=login))
            
            godzina_rozpoczecia_nadgodzin = request.form['godzina_rozpoczecia_nadgodzin']
            godzina_zakonczenia_nadgodzin = request.form['godzina_zakonczenia_nadgodzin']
            
            # Oblicz czas nadgodzin
            czas_nadgodzin = oblicz_czas_pracy(godzina_rozpoczecia_nadgodzin, godzina_zakonczenia_nadgodzin)
            
            # Aktualizuj raport
            raport['godzina_rozpoczecia_nadgodzin'] = godzina_rozpoczecia_nadgodzin
            raport['godzina_zakonczenia_nadgodzin'] = godzina_zakonczenia_nadgodzin
            raport['czas_nadgodzin'] = czas_nadgodzin
            
            # Przelicz całkowity czas
            calkowity_czas = raport.get('czas_pracy', 0) + raport.get('czas_zdalnej', 0) + czas_nadgodzin
            raport['calkowity_czas'] = round(calkowity_czas, 1)
            
            system.zapisz_dane()
            flash('Nadgodziny zostały dodane!', 'success')
            return redirect(url_for('raporty_pracownika', login=login))
    
    # Jeśli nie znaleziono raportu
    flash('Nie można dodać nadgodzin - brak raportu dla wybranego dnia!', 'error')
    return redirect(url_for('raporty_pracownika', login=login))

@app.route('/sprawdz_raport_nadgodziny/<data>')
def sprawdz_raport_nadgodziny(data):
    if 'uzytkownik' not in session:
        return jsonify({'success': False, 'message': 'Brak uprawnień!'})
    
    # Sprawdź czy raport istnieje dla danego użytkownika i daty
    raporty_uzytkownika = system.raporty.get(session['uzytkownik'], [])
    for raport in raporty_uzytkownika:
        if raport['data'] == data:
            if raport.get('dzien_wolny'):
                return jsonify({'success': False, 'message': 'Nie można dodać nadgodzin do dnia wolnego!'})
            return jsonify({'success': True})
    
    return jsonify({'success': False, 'message': 'Brak raportu dla wybranego dnia! Najpierw dodaj standardowy raport pracy.'})

def zlicz_dni_wolne(login):
    if login not in system.raporty:
        return 0
        
    dni_wolne = 0
    for raport in system.raporty[login]:
        if raport.get('dzien_wolny') and raport.get('typ_wolnego') != 'za święto':
            dni_wolne += 1
            
    return dni_wolne

def sprawdz_poprawnosc_godzin(form_data):
    """
    Sprawdza czy formularz zawiera prawidłową kombinację godzin.
    Zwraca (bool, str) - (czy_poprawne, komunikat_błędu)
    """
    # Jeśli to dzień wolny, wszystko jest ok
    if 'dzien_wolny' in form_data:
        return True, ""
    
    # Sprawdź czy godziny są parami (rozpoczęcie i zakończenie)
    godzina_rozpoczecia = form_data.get('godzina_rozpoczecia', '')
    godzina_zakonczenia = form_data.get('godzina_zakonczenia', '')
    godzina_rozpoczecia_zdalnej = form_data.get('godzina_rozpoczecia_zdalnej', '')
    godzina_zakonczenia_zdalnej = form_data.get('godzina_zakonczenia_zdalnej', '')
    godzina_rozpoczecia_nadgodzin = form_data.get('godzina_rozpoczecia_nadgodzin', '')
    godzina_zakonczenia_nadgodzin = form_data.get('godzina_zakonczenia_nadgodzin', '')
    
    # Sprawdź standardowe godziny
    if bool(godzina_rozpoczecia) != bool(godzina_zakonczenia):
        return False, "Musisz wprowadzić zarówno godzinę rozpoczęcia jak i zakończenia dla standardowych godzin pracy."
    
    # Sprawdź zdalne godziny
    if bool(godzina_rozpoczecia_zdalnej) != bool(godzina_zakonczenia_zdalnej):
        return False, "Musisz wprowadzić zarówno godzinę rozpoczęcia jak i zakończenia dla pracy zdalnej."
    
    # Sprawdź nadgodziny
    if bool(godzina_rozpoczecia_nadgodzin) != bool(godzina_zakonczenia_nadgodzin):
        return False, "Musisz wprowadzić zarówno godzinę rozpoczęcia jak i zakończenia dla nadgodzin."
    
    # Sprawdź czy są standardowe lub zdalne jeśli są nadgodziny
    ma_standardowe = bool(godzina_rozpoczecia and godzina_zakonczenia)
    ma_zdalne = bool(godzina_rozpoczecia_zdalnej and godzina_zakonczenia_zdalnej)
    ma_nadgodziny = bool(godzina_rozpoczecia_nadgodzin and godzina_zakonczenia_nadgodzin)
    
    if ma_nadgodziny and not (ma_standardowe or ma_zdalne):
        return False, "Aby dodać nadgodziny, musisz wprowadzić też standardowe godziny pracy lub pracę zdalną."
    
    return True, ""

@app.route('/edytuj_godziny/<login>/<data>', methods=['POST'])
def edytuj_godziny(login, data):
    if 'uzytkownik' not in session or not session['admin']:
        flash('Brak uprawnień!', 'error')
        return redirect(url_for('index'))
    
    # Sprawdź poprawność danych
    poprawne, komunikat = sprawdz_poprawnosc_godzin(request.form)
    if not poprawne:
        flash(komunikat, 'error')
        return redirect(url_for('raporty_pracownika', login=login))
    
    if login not in system.raporty:
        flash('Nie znaleziono raportów dla tego użytkownika!', 'error')
        return redirect(url_for('raporty_pracownika', login=login))
    
    for raport in system.raporty[login]:
        if raport['data'] == data:
            # Sprawdź czy to dzień wolny
            dzien_wolny = 'dzien_wolny' in request.form
            
            if dzien_wolny:
                raport.update({
                    'dzien_wolny': True,
                    'typ_wolnego': request.form.get('typ_wolnego', 'zwykłe'),
                    'godzina_rozpoczecia': None,
                    'godzina_zakonczenia': None,
                    'godzina_rozpoczecia_zdalnej': None,
                    'godzina_zakonczenia_zdalnej': None,
                    'godzina_rozpoczecia_nadgodzin': None,
                    'godzina_zakonczenia_nadgodzin': None,
                    'czas_pracy': 8.0,  # Ustawienie 8 godzin dla dnia wolnego
                    'czas_zdalnej': 0,
                    'czas_nadgodzin': 0,
                    'calkowity_czas': 8.0  # Całkowity czas również 8 godzin
                })
            else:
                # Pobierz wszystkie godziny z formularza
                godzina_rozpoczecia = request.form.get('godzina_rozpoczecia', '')
                godzina_zakonczenia = request.form.get('godzina_zakonczenia', '')
                godzina_rozpoczecia_zdalnej = request.form.get('godzina_rozpoczecia_zdalnej', '')
                godzina_zakonczenia_zdalnej = request.form.get('godzina_zakonczenia_zdalnej', '')
                godzina_rozpoczecia_nadgodzin = request.form.get('godzina_rozpoczecia_nadgodzin', '')
                godzina_zakonczenia_nadgodzin = request.form.get('godzina_zakonczenia_nadgodzin', '')

                # Oblicz czasy dla każdego typu pracy
                czas_pracy = oblicz_czas_pracy(godzina_rozpoczecia, godzina_zakonczenia) if godzina_rozpoczecia and godzina_zakonczenia else 0
                czas_zdalnej = oblicz_czas_pracy(godzina_rozpoczecia_zdalnej, godzina_zakonczenia_zdalnej) if godzina_rozpoczecia_zdalnej and godzina_zakonczenia_zdalnej else 0
                czas_nadgodzin = oblicz_czas_pracy(godzina_rozpoczecia_nadgodzin, godzina_zakonczenia_nadgodzin) if godzina_rozpoczecia_nadgodzin and godzina_zakonczenia_nadgodzin else 0

                raport.update({
                    'dzien_wolny': False,
                    'typ_wolnego': None,
                    'godzina_rozpoczecia': godzina_rozpoczecia or None,
                    'godzina_zakonczenia': godzina_zakonczenia or None,
                    'godzina_rozpoczecia_zdalnej': godzina_rozpoczecia_zdalnej or None,
                    'godzina_zakonczenia_zdalnej': godzina_zakonczenia_zdalnej or None,
                    'godzina_rozpoczecia_nadgodzin': godzina_rozpoczecia_nadgodzin or None,
                    'godzina_zakonczenia_nadgodzin': godzina_zakonczenia_nadgodzin or None,
                    'czas_pracy': czas_pracy,
                    'czas_zdalnej': czas_zdalnej,
                    'czas_nadgodzin': czas_nadgodzin,
                    'calkowity_czas': round(czas_pracy + czas_zdalnej + czas_nadgodzin, 1)
                })
            
            system.zapisz_dane()
            flash('Raport został zaktualizowany!', 'success')
            return redirect(url_for('raporty_pracownika', login=login))
    
    flash('Nie znaleziono raportu dla wybranej daty!', 'error')
    return redirect(url_for('raporty_pracownika', login=login))

@app.route('/edytuj_raport/<string:data>', methods=['GET', 'POST'])
def edytuj_raport(data):
    if 'uzytkownik' not in session:
        return redirect(url_for('logowanie'))
    
    if request.method == 'POST':
        print("Otrzymane dane:", request.form)  # Debugging
        is_dzien_wolny = request.form.get('is_dzien_wolny') == 'on'
        dzien_wolny = request.form.get('dzien_wolny')
        
        nowy_raport = {
            'data': data
        }
        
        if is_dzien_wolny and dzien_wolny:
            nowy_raport['dzien_wolny'] = dzien_wolny
        else:
            nowy_raport.update({
                'godzina_rozpoczecia': request.form.get('godzina_rozpoczecia'),
                'godzina_zakonczenia': request.form.get('godzina_zakonczenia'),
                'godzina_rozpoczecia_nadgodzin': request.form.get('godzina_rozpoczecia_nadgodzin'),
                'godzina_zakonczenia_nadgodzin': request.form.get('godzina_zakonczenia_nadgodzin'),
                'godzina_rozpoczecia_zdalnej': request.form.get('godzina_rozpoczecia_zdalnej'),
                'godzina_zakonczenia_zdalnej': request.form.get('godzina_zakonczenia_zdalnej')
            })
        
        print("Nowy raport:", nowy_raport)  # Debugging
        
        # Aktualizuj raport
        raporty_uzytkownika = system.raporty.get(session['uzytkownik'], [])
        for i, r in enumerate(raporty_uzytkownika):
            if r['data'] == data:
                system.raporty[session['uzytkownik']][i] = nowy_raport
                break
        
        system.zapisz_dane()
        flash('Raport został zaktualizowany!', 'success')
        return redirect(url_for('moje_raporty'))
    
    return render_template('moje_raporty.html')

def migruj_stare_raporty():
    """Dodaje brakujące pola do starych raportów"""
    for login, raporty_uzytkownika in system.raporty.items():
        for raport in raporty_uzytkownika:
            if 'calkowity_czas' not in raport:
                raport['calkowity_czas'] = 0
            if 'czas_pracy' not in raport:
                raport['czas_pracy'] = 0
            if 'czas_zdalnej' not in raport:
                raport['czas_zdalnej'] = 0
            if 'czas_nadgodzin' not in raport:
                raport['czas_nadgodzin'] = 0
    system.zapisz_dane()

def migruj_stare_konta():
    """Dodaje brakujące pola do starych kont użytkowników"""
    for login, dane in system.uzytkownicy.items():
        if 'imie' not in dane:
            dane['imie'] = login
        if 'nazwisko' not in dane:
            dane['nazwisko'] = ''
        if 'wyswietlana_nazwa' not in dane:
            dane['wyswietlana_nazwa'] = f"{dane['imie']} {dane['nazwisko']}".strip() or login
    system.zapisz_dane()

def godziny_na_hhmm(czas_w_godzinach):
    """Konwertuje czas z formatu dziesiętnego na format HH:MM"""
    if czas_w_godzinach is None:
        return "00:00"
    
    godziny = int(czas_w_godzinach)
    minuty = int((czas_w_godzinach - godziny) * 60)
    return f"{godziny:02d}:{minuty:02d}"

# Dodaj funkcję do kontekstu szablonu
@app.context_processor
def utility_processor():
    return dict(godziny_na_hhmm=godziny_na_hhmm)

@app.route('/edytuj_profil', methods=['GET', 'POST'])
def edytuj_profil():
    if 'uzytkownik' not in session:
        return redirect(url_for('logowanie'))
    
    login = session['uzytkownik']
    
    if request.method == 'POST':
        stare_haslo = request.form.get('stare_haslo')
        nowe_haslo = request.form.get('nowe_haslo', '')
        potwierdz_haslo = request.form.get('potwierdz_haslo', '')
        imie = request.form.get('imie')
        nazwisko = request.form.get('nazwisko')
        
        # Sprawdź czy stare hasło jest poprawne
        if system.uzytkownicy[login]['haslo'] != stare_haslo:
            flash('Nieprawidłowe obecne hasło!', 'error')
            return redirect(url_for('edytuj_profil'))
        
        # Aktualizuj dane profilu
        system.uzytkownicy[login].update({
            'imie': imie,
            'nazwisko': nazwisko,
            'wyswietlana_nazwa': f"{imie} {nazwisko}"
        })
        
        # Jeśli podano nowe hasło, zaktualizuj je
        if nowe_haslo:
            if nowe_haslo != potwierdz_haslo:
                flash('Nowe hasła nie są identyczne!', 'error')
                return redirect(url_for('edytuj_profil'))
            system.uzytkownicy[login]['haslo'] = nowe_haslo
        
        system.zapisz_dane()
        flash('Profil został zaktualizowany!', 'success')
        return redirect(url_for('moje_raporty'))
    
    return render_template('edytuj_profil.html', uzytkownik=system.uzytkownicy[login])

@app.route('/przypomnij_haslo', methods=['GET', 'POST'])
def przypomnij_haslo():
    if request.method == 'POST':
        login = request.form.get('login')
        
        if login in system.uzytkownicy:
            # W prawdziwej aplikacji tutaj wysłalibyśmy email
            # Na potrzeby demonstracji po prostu resetujemy hasło na "haslo123"
            nowe_haslo = "haslo123"
            system.uzytkownicy[login]['haslo'] = nowe_haslo
            system.zapisz_dane()
            
            flash(f'Hasło zostało zresetowane na: {nowe_haslo}', 'success')
            return redirect(url_for('logowanie'))
        else:
            flash('Nie znaleziono użytkownika o podanym loginie!', 'error')
    
    return render_template('przypomnij_haslo.html')

def formatuj_date(data_str):
    # Słownik z polskimi nazwami dni tygodnia
    dni_tygodnia = {
        0: 'Poniedziałek',
        1: 'Wtorek',
        2: 'Środa',
        3: 'Czwartek',
        4: 'Piątek',
        5: 'Sobota',
        6: 'Niedziela'
    }
    
    # Konwertuj string na obiekt daty
    data = datetime.strptime(data_str, '%Y-%m-%d')
    # Pobierz nazwę dnia tygodnia
    dzien = dni_tygodnia[data.weekday()]
    # Zwróć sformatowany string
    return f"{dzien} {data_str}"

# Dodaj funkcję jako filtr Jinja2
app.jinja_env.filters['formatuj_date'] = formatuj_date 
  
@app.route('/edytuj_raport/<login>/<data>', methods=['POST'])
def edytuj_raport_pracownika(login, data):
    print(f"\n=== Edycja raportu dla {login} na dzień {data} ===")
    print("Dane formularza:", dict(request.form))
    
    if not czy_admin(session['uzytkownik']):
        flash('Brak uprawnień do edycji raportu!', 'danger')
        return redirect(url_for('index'))

    try:
        # Używamy globalnej instancji system
        print("Stan systemu przed edycją:", system.raporty.get(login, []))

        # Inicjalizacja struktury danych jeśli nie istnieje
        if login not in system.raporty:
            system.raporty[login] = []

        # Tworzenie nowego raportu
        is_dzien_wolny = request.form.get('is_dzien_wolny') == 'on'
        if is_dzien_wolny:
            nowy_raport = {
                'dzien_wolny': request.form.get('dzien_wolny'),
                'data': data
            }
        else:
            nowy_raport = {
                'godzina_rozpoczecia': request.form.get('godzina_rozpoczecia'),
                'godzina_zakonczenia': request.form.get('godzina_zakonczenia'),
                'godzina_rozpoczecia_nadgodzin': request.form.get('godzina_rozpoczecia_nadgodzin'),
                'godzina_zakonczenia_nadgodzin': request.form.get('godzina_zakonczenia_nadgodzin'),
                'godzina_rozpoczecia_zdalnej': request.form.get('godzina_rozpoczecia_zdalnej'),
                'godzina_zakonczenia_zdalnej': request.form.get('godzina_zakonczenia_zdalnej'),
                'data': data
            }

        # Aktualizacja raportu w systemie
        # Znajdź i zaktualizuj istniejący raport lub dodaj nowy
        raport_znaleziony = False
        for i, raport in enumerate(system.raporty[login]):
            if raport.get('data') == data:
                system.raporty[login][i] = nowy_raport
                raport_znaleziony = True
                break
        
        if not raport_znaleziony:
            system.raporty[login].append(nowy_raport)
        
        # Zapisz zmiany
        system.zapisz_dane()
        
        print("Nowy raport do zapisania:", nowy_raport)
        print("Stan systemu po aktualizacji:", system.raporty[login])

        flash('Raport został zaktualizowany', 'success')
        return redirect(url_for('raporty_pracownika', login=login))

    except Exception as e:
        print(f"BŁĄD: {str(e)}")
        import traceback
        print(traceback.format_exc())
        flash(f'Wystąpił błąd podczas edycji raportu: {str(e)}', 'danger')
        return redirect(url_for('raporty_pracownika', login=login))

@app.template_filter('split_first')
def split_first(value):
    """Zwraca pierwszą część tekstu przed spacją"""
    return value.split(' ')[0] if value else ''


@app.route('/usun_raport/<login>/<data>', methods=['POST'])
@wymaga_zalogowania
def usun_raport_pracownika(login, data):
    print(f"\n=== Próba usunięcia raportu ===")
    print(f"Login: {login}")
    print(f"Data: {data}")
    
    if not czy_admin(session['uzytkownik']):
        print("Brak uprawnień administratora")
        flash('Brak uprawnień do usunięcia raportu!', 'danger')
        return redirect(url_for('index'))

    try:
        # Używamy globalnej instancji system zamiast wczytywać nową
        print(f"Struktura raportów dla {login}:", system.raporty.get(login, {}))
        
        if login in system.raporty:
            raporty_pracownika = system.raporty[login]
            # Szukamy raportu z daną datą
            for i, raport in enumerate(raporty_pracownika):
                if raport.get('data') == data:
                    del raporty_pracownika[i]
                    system.zapisz_dane()
                    print(f"Raport usunięty pomyślnie")
                    flash('Raport został usunięty', 'success')
                    break
            else:
                print(f"Nie znaleziono raportu dla daty {data}")
                flash('Nie znaleziono raportu do usunięcia', 'warning')
        else:
            print(f"Nie znaleziono raportów dla użytkownika {login}")
            flash('Nie znaleziono raportów tego użytkownika', 'warning')
        
        return redirect(url_for('raporty_pracownika', login=login))
        
    except Exception as e:
        print(f"Błąd podczas usuwania raportu: {str(e)}")
        import traceback
        print(traceback.format_exc())
        flash('Wystąpił błąd podczas usuwania raportu', 'danger')
        return redirect(url_for('raporty_pracownika', login=login))

def przygotuj_dane_tygodnia(selected_week):
    # Konwertuj string daty na obiekt date
    selected_date = datetime.strptime(selected_week, '%Y-%m-%d').date()
    
    # Znajdź początek tygodnia (poniedziałek)
    start_of_week = selected_date - timedelta(days=selected_date.weekday())
    
    # Przygotuj listę dat dla całego tygodnia
    week_dates = [(start_of_week + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]
    
    # Przygotuj słownik raportów dla wybranego tygodnia
    reports_by_date = {}
    
    # Formatuj daty początku i końca tygodnia
    current_week_start = start_of_week.strftime('%Y-%m-%d')
    current_week_end = (start_of_week + timedelta(days=6)).strftime('%Y-%m-%d')
    
    return week_dates, reports_by_date, current_week_start, current_week_end

@app.route('/pobierz_raport_pdf/<login>')
@wymaga_zalogowania
def pobierz_raport_pdf(login):
    if not czy_admin(session['uzytkownik']):
        flash('Brak uprawnień!', 'danger')
        return redirect(url_for('index'))

    try:
        # Pobierz parametr week z URL
        selected_week = request.args.get('week')
        if not selected_week:
            selected_week = datetime.now().strftime('%Y-%m-%d')

        # Przygotuj dane tygodnia
        week_dates, reports_by_date, current_week_start, current_week_end = przygotuj_dane_tygodnia(selected_week)
        
        # Pobierz raporty dla danego pracownika
        if login in system.raporty:
            for raport in system.raporty[login]:
                if raport['data'] in week_dates:
                    reports_by_date[raport['data']] = raport

        # Przygotuj HTML dla PDF
        html_content = render_template(
            'raport_pdf.html',
            login=login,
            system=system,
            week_dates=week_dates,
            reports_by_date=reports_by_date,
            current_week_start=current_week_start,
            current_week_end=current_week_end,
            dni_wolne=DNI_WOLNE
        )

        # Konfiguracja dla pdfkit
        options = {
            'page-size': 'A4',
            'margin-top': '0.75in',
            'margin-right': '0.75in',
            'margin-bottom': '0.75in',
            'margin-left': '0.75in',
            'encoding': 'UTF-8',
            'no-outline': None
        }

        # Utwórz tymczasowy plik PDF
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as pdf_file:
            # Użyj konfiguracji przy generowaniu PDF
            pdfkit.from_string(html_content, pdf_file.name, options=options, configuration=config)
            
            # Przygotuj nazwę pliku do pobrania
            filename = f"raport_{login}_{current_week_start}_{current_week_end}.pdf"
            
            return send_file(
                pdf_file.name,
                as_attachment=True,
                download_name=filename,
                mimetype='application/pdf'
            )

    except Exception as e:
        print(f"Błąd podczas generowania PDF: {str(e)}")
        import traceback
        print(traceback.format_exc())
        flash(f'Wystąpił błąd podczas generowania PDF: {str(e)}', 'danger')
        return redirect(url_for('raporty_pracownika', login=login))

# Na początku pliku, po importach
DNI_WOLNE = {
    'DW': 'Dzień wolny',
    'CH': 'Chorobowe',
    'WŚ': 'Wolne świąteczne',
    'NŻ': 'Urlop na żądanie',
    True: 'Dzień wolny',  # dla przypadku gdy dzien_wolny jest boolean
    False: '',  # dla przypadku gdy dzien_wolny jest boolean
    None: ''
}

# Dodaj wywołanie migracji przy starcie aplikacji
if __name__ == '__main__':
    migruj_stare_raporty()
    migruj_stare_konta()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port) 
