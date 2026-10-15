export const GENDERS = [
  { value: 'male', label: 'Male' },
  { value: 'female', label: 'Female' },
  { value: 'other', label: 'Other' },
  { value: 'prefer_not_to_say', label: 'Prefer not to say' },
]

export const BLOOD_GROUPS = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']
  .map((g) => ({ value: g, label: g }))
  .concat({ value: 'unknown', label: 'Unknown' })

export const RELATIONSHIPS = [
  { value: 'self', label: 'Self' },
  { value: 'spouse', label: 'Spouse' },
  { value: 'child', label: 'Child' },
  { value: 'parent', label: 'Parent' },
  { value: 'sibling', label: 'Sibling' },
  { value: 'other', label: 'Other' },
]

export const SEVERITIES = [
  { value: 'mild', label: 'Mild' },
  { value: 'moderate', label: 'Moderate' },
  { value: 'severe', label: 'Severe' },
]

export const labelOf = (options, value) => options.find((o) => o.value === value)?.label ?? value ?? '-'

export const CONSENT_ITEMS = [
  {
    key: 'data_storage',
    label: 'Store my health data',
    description: 'Keep this patient record and medical history at the clinic.',
    required: true,
  },
  {
    key: 'voice_recording',
    label: 'Voice recording',
    description: 'Record conversations with the clinic voice assistant.',
  },
  {
    key: 'ai_processing',
    label: 'AI processing',
    description: 'Let AI models analyse voice and health data to assist doctors.',
  },
]
