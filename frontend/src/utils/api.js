import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 120000,
})

export const getStats = () => api.get('/stats').then(r => r.data)
export const getVideos = (page = 1) => api.get(`/videos?page=${page}`).then(r => r.data)
export const getVideo = (id) => api.get(`/videos/${id}`).then(r => r.data)
export const getVideoMessages = (id) => api.get(`/videos/${id}/messages`).then(r => r.data)
export const processVideo = (url, language = 'en') =>
  api.post('/process', { url, language }).then(r => r.data)
export const getSessions = () => api.get('/sessions').then(r => r.data)
export const getHealth = () => api.get('/health').then(r => r.data)

export default api
