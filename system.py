import os
import json

class SystemRaportowania:
    def __init__(self):
        self.uzytkownicy = {}
        self.raporty = {}
        self.wczytaj_dane()

    def wczytaj_dane(self):
        if os.environ.get('RENDER'):
            # Wczytaj dane z zmiennych środowiskowych
            try:
                self.uzytkownicy = json.loads(os.environ.get('USERS_DATA', '{}'))
                self.raporty = json.loads(os.environ.get('REPORTS_DATA', '{}'))
            except json.JSONDecodeError:
                self.uzytkownicy = {}
                self.raporty = {}
        else:
            # Wczytaj dane z pliku lokalnie
            try:
                with open('dane.json', 'r', encoding='utf-8') as f:
                    dane = json.load(f)
                    self.uzytkownicy = dane.get('uzytkownicy', {})
                    self.raporty = dane.get('raporty', {})
            except FileNotFoundError:
                self.uzytkownicy = {}
                self.raporty = {}

    def zapisz_dane(self):
        if os.environ.get('RENDER'):
            # W środowisku Render dane będą tymczasowe
            # Docelowo należy użyć bazy danych
            pass
        else:
            # Zapisz dane do pliku lokalnie
            with open('dane.json', 'w', encoding='utf-8') as f:
                json.dump({
                    'uzytkownicy': self.uzytkownicy,
                    'raporty': self.raporty
                }, f, ensure_ascii=False, indent=4)

    def pobierz_raporty_pracownika(self, login):
        """Pobiera wszystkie raporty dla danego pracownika"""
        if login in self.raporty:
            # Sortuj raporty po dacie
            return sorted(self.raporty[login], key=lambda x: x['data'], reverse=True)
        return []
