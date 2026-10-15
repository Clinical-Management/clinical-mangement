import { useEffect, useState } from 'react'
import { listDoctors } from '../../api/doctors'
import { inputClass } from '../ui'

export default function DoctorSelect({ value, onChange, allowAll = false, className = inputClass }) {
  const [doctors, setDoctors] = useState([])

  useEffect(() => {
    listDoctors().then(setDoctors)
  }, [])

  return (
    <select className={className} required={!allowAll} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{allowAll ? 'All doctors' : 'Select a doctor'}</option>
      {doctors.map((d) => (
        <option key={d.id} value={d.id}>
          {d.full_name}
          {d.specialization && ` - ${d.specialization}`}
        </option>
      ))}
    </select>
  )
}
