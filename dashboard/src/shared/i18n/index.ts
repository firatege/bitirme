import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import { resources } from './resources';

void i18n.use(initReactI18next).init({
  resources,
  lng: 'tr',
  fallbackLng: 'tr',
  defaultNS: 'common',
  interpolation: { escapeValue: false },
});

export { i18n };
