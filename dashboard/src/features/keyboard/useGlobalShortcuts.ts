import { useNavigate } from 'react-router-dom';
import { useHotkeys } from 'react-hotkeys-hook';

export function useGlobalShortcuts(): void {
  const navigate = useNavigate();

  useHotkeys('g+d', () => navigate('/'));
  useHotkeys('g+r', () => navigate('/runs'));
  useHotkeys('g+c', () => navigate('/cart'));
  useHotkeys('g+a', () => navigate('/analytics'));
  useHotkeys('g+s', () => navigate('/settings'));

  useHotkeys('/', (e) => {
    e.preventDefault();
    const el = document.querySelector<HTMLInputElement>(
      'input[data-search-input]',
    );
    el?.focus();
  });
}
