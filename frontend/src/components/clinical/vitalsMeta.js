export const VITALS = [
  { key: 'bp', label: 'Blood pressure', unit: 'mmHg' },
  { key: 'pulse', label: 'Pulse', unit: 'bpm' },
  { key: 'temperature_c', label: 'Temperature', unit: '°C' },
  { key: 'spo2', label: 'SpO2', unit: '%' },
  { key: 'weight_kg', label: 'Weight', unit: 'kg' },
  { key: 'height_cm', label: 'Height', unit: 'cm' },
  { key: 'bmi', label: 'BMI', unit: 'kg/m²' },
]

// Status colours are reserved for abnormal values and always come with an icon + word
export const FLAG_META = {
  high: { label: 'High', icon: '▲', text: 'text-amber-800', chip: 'bg-amber-100 text-amber-800', ring: '#b45309' },
  low: { label: 'Low', icon: '▼', text: 'text-amber-800', chip: 'bg-amber-100 text-amber-800', ring: '#b45309' },
  critical_high: { label: 'Critical high', icon: '!!', text: 'text-red-700', chip: 'bg-red-100 text-red-700', ring: '#b91c1c' },
  critical_low: { label: 'Critical low', icon: '!!', text: 'text-red-700', chip: 'bg-red-100 text-red-700', ring: '#b91c1c' },
}

// Validated categorical pair (brand navy step + brand teal) for chart series
export const SERIES_COLORS = ['#1a5ea6', '#039583']

export const worstFlag = (...flags) =>
  flags.find((f) => f?.startsWith('critical')) ?? flags.find(Boolean) ?? null

export const formatReading = (reading, key) => {
  if (key === 'bp') {
    return reading.bp_systolic != null ? `${reading.bp_systolic}/${reading.bp_diastolic}` : null
  }
  return reading[key] ?? null
}

export const readingFlag = (reading, key) =>
  key === 'bp' ? worstFlag(reading.flags.bp_systolic, reading.flags.bp_diastolic) : reading.flags[key]
