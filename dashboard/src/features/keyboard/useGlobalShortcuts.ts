import { useHotkeys } from 'react-hotkeys-hook';
import { useNavigate } from 'react-router-dom';

/** Register global keyboard shortcuts for navigation. */
export function useGlobalShortcuts() {
  const navigate = useNavigate();

  useHotkeys('g d', () => navigate('/'), { preventDefault: true });
  useHotkeys('g r', () => navigate('/runs'), { preventDefault: true });
  useHotkeys('g c', () => navigate('/cart'), { preventDefault: true });
  useHotkeys('g a', () => navigate('/analytics'), { preventDefault: true });
  useHotkeys('g s', () => navigate('/settings'), { preventDefault: true });
}
