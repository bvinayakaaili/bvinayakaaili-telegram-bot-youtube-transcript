import { Routes, Route } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import Videos from './pages/Videos'
import VideoDetail from './pages/VideoDetail'
import Sessions from './pages/Sessions'
import Playground from './pages/Playground'

export default function App() {
  return (
    <div className="flex min-h-screen bg-surface-0">
      <Sidebar />
      <main className="ml-60 flex-1 p-8 min-h-screen">
        <div className="max-w-6xl mx-auto">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/videos" element={<Videos />} />
            <Route path="/videos/:id" element={<VideoDetail />} />
            <Route path="/sessions" element={<Sessions />} />
            <Route path="/playground" element={<Playground />} />
          </Routes>
        </div>
      </main>
    </div>
  )
}