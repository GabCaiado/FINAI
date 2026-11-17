import Footer from './components/Footer'
import { ptBR } from './i18n/pt-BR'

export default function App() {
  return (
    <div className="flex min-h-screen flex-col">
      <main className="mx-auto w-full max-w-3xl flex-1 p-4">
        <h1 className="text-2xl font-bold">{ptBR.appName}</h1>
        <p className="mt-2 text-slate-600">{ptBR.tagline}</p>
      </main>
      <Footer />
    </div>
  )
}
