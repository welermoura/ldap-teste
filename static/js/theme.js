
/*!
 * Color mode toggler for Bootstrap's docs (https://getbootstrap.com/)
 * Copyright 2011-2024 The Bootstrap Authors
 * Licensed under the Creative Commons Attribution 3.0 Unported License.
 */

(() => {
  'use strict'

  const getStoredTheme = () => localStorage.getItem('theme')
  const setStoredTheme = theme => localStorage.setItem('theme', theme)

  const getPreferredTheme = () => {
    const storedTheme = getStoredTheme()
    if (storedTheme) {
      return storedTheme
    }

    // Default to dark theme if no preference is found
    return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
  }

  const setTheme = theme => {
    if (theme === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      document.documentElement.setAttribute('data-bs-theme', 'dark')
    } else {
      document.documentElement.setAttribute('data-bs-theme', theme)
    }
  }

  const updateToggleButton = (theme) => {
    const themeToggle = document.getElementById('theme-toggle');
    if (!themeToggle) return;

    const themeToggleIcon = themeToggle.querySelector('i');
    if (theme === 'dark') {
        themeToggleIcon.className = 'fa-regular fa-sun';
        themeToggle.classList.add('theme-icon-sun');
    } else {
        themeToggleIcon.className = 'fas fa-moon';
        themeToggle.classList.remove('theme-icon-sun');
    }
  }

  // Set theme on initial load
  const initialTheme = getPreferredTheme();
  setTheme(initialTheme);

  // Update UI and attach event listener after DOM is loaded
  document.addEventListener('DOMContentLoaded', () => {
    updateToggleButton(getPreferredTheme());

    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
      themeToggle.addEventListener('click', () => {
        const currentTheme = getStoredTheme() || getPreferredTheme();
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        setStoredTheme(newTheme);
        setTheme(newTheme);
        updateToggleButton(newTheme);
      });
    }
  });

})();
