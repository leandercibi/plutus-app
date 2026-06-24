import axios from 'axios'
import { useAuthStore } from '../store/auth'

export const apiClient = axios.create({
  baseURL: '/api',
  timeout: 30_000,
})

apiClient.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().clearToken()
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)
