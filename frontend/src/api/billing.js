import api from './client'

// Money is in paise everywhere in the API
const bill = (id) => `/appointments/${id}/bill`

export const getBill = (id) => api.get(bill(id)).then((r) => r.data)
export const saveBill = (id, payload) => api.put(bill(id), payload).then((r) => r.data)
export const takePayment = (id, payload) => api.post(`${bill(id)}/payments`, payload).then((r) => r.data)
export const decideConcession = (id, decision) => api.post(`${bill(id)}/concession/${decision}`).then((r) => r.data)
export const requestRefund = (id, payload) => api.post(`${bill(id)}/refunds`, payload).then((r) => r.data)
export const decideRefund = (id, refundId, decision) => api.post(`${bill(id)}/refunds/${refundId}/${decision}`).then((r) => r.data)
export const cancelBill = (id, reason) => api.post(`${bill(id)}/cancel`, { reason }).then((r) => r.data)

export const listReceipts = (id) => api.get(`/appointments/${id}/receipts`).then((r) => r.data)
export const fetchReceiptPdf = (receiptId, fmt = 'a5') => api.get(`/receipts/${receiptId}/pdf`, { params: { fmt }, responseType: 'blob' }).then((r) => r.data)
export const deliverReceipt = (receiptId, payload) => api.post(`/receipts/${receiptId}/deliver`, payload).then((r) => r.data)
export const patientBills = (patientId) => api.get(`/patients/${patientId}/bills`).then((r) => r.data)

export const getCollections = (date) => api.get('/billing/collections', { params: { date } }).then((r) => r.data)
export const reconcile = (payload) => api.post('/billing/reconciliations', payload).then((r) => r.data)
export const exportReceipts = (params) => api.get('/billing/export', { params, responseType: 'blob' }).then((r) => r.data)
export const listDues = () => api.get('/billing/dues').then((r) => r.data)
export const listApprovals = () => api.get('/billing/approvals').then((r) => r.data)

export const getBillingSettings = () => api.get('/billing/settings').then((r) => r.data)
export const saveBillingSettings = (payload) => api.put('/billing/settings', payload).then((r) => r.data)
export const listServices = (all = false) => api.get('/billing/services', { params: { all } }).then((r) => r.data)
export const addService = (payload) => api.post('/billing/services', payload).then((r) => r.data)
export const updateService = (id, payload) => api.put(`/billing/services/${id}`, payload).then((r) => r.data)
