import { ptBR } from '../i18n/pt-BR'

export default function Footer() {
  return (
    <footer className="border-t border-slate-200 p-4 text-center text-xs text-slate-600">
      {ptBR.footerDisclaimer}
    </footer>
  )
}
