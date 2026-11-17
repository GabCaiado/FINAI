import Footer from './components/Footer'

export default function App() {
  return (
    <div className="flex min-h-screen flex-col">
      <main className="mx-auto w-full max-w-3xl flex-1 p-4">
        <h1 className="text-2xl font-bold">FINAI</h1>
        <p className="mt-2 text-slate-600">Organize suas finanças com ajuda de IA.</p>
      </main>
      <Footer />
    </div>
  )
}
