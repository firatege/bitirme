import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import { resources } from './resources';

const saved = typeof localStorage !== 'undefined'
  ? localStorage.getItem('lang')
  : null;

void i18n.use(initReactI18next).init({
  resources,
  lng: saved ?? 'tr',
  fallbackLng: 'tr',
  defaultNS: 'common',
  interpolation: { escapeValue: false },
});

export { i18n };

export function setLanguage(lng: 'tr' | 'en') {
  void i18n.changeLanguage(lng);
  try {
    localStorage.setItem('lang', lng);
  } catch {
    /* ignore */
  }
}
