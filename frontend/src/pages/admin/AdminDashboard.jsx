import FrontDeskDashboard from '../../components/dashboard/FrontDeskDashboard'

export default function AdminDashboard() {
  return (
    <FrontDeskDashboard
      title="Clinic overview"
      extraActions={[
        { to: '/admin/doctors', label: 'Doctors' },
        { to: '/admin/holidays', label: 'Holidays' },
      ]}
    />
  )
}
