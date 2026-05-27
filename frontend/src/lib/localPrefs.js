export function readLocalPref(key, fallback, isValid = () => true) {
  try {
    const raw = localStorage.getItem(key)
    if (raw === null) return fallback
    return isValid(raw) ? raw : fallback
  } catch {
    return fallback
  }
}

export function writeLocalPref(key, value) {
  try {
    localStorage.setItem(key, value)
  } catch {
    // localStorage may be unavailable in private mode or restricted browsers.
  }
}

export function readLocalBool(key, fallback = false) {
  const raw = readLocalPref(key, fallback ? '1' : '0', value => value === '1' || value === '0')
  return raw === '1'
}

export function writeLocalBool(key, value) {
  writeLocalPref(key, value ? '1' : '0')
}
