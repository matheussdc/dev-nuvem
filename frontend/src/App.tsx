import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, Assentos, brl, clientId, duracao, erroMsg, Filme } from "./api";

const FILEIRAS = ["G", "F", "E", "D", "C", "B", "A"]; // G perto da tela, como na inspiração
const LUGARES = Array.from({ length: 16 }, (_, i) => i + 1);
const VAZIO: Assentos = { vendidos: [], reservados: [], meus: [] };

const iso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const diaSemana = (d: Date) => {
  const s = d.toLocaleDateString("pt-BR", { weekday: "short" }).replace(".", "");
  return s[0].toUpperCase() + s.slice(1);
};
const ordemAssento = (a: string, b: string) =>
  a[0] === b[0] ? Number(a.slice(1)) - Number(b.slice(1)) : a.localeCompare(b);

const ICONES = {
  menu: "M4 7h16M4 12h16M4 17h16",
  filtro: "M6 4v16M18 4v16M12 4v16M4 9h4M10 15h4M16 8h4",
  ingresso: "M4 7h16v3a2 2 0 0 0 0 4v3H4v-3a2 2 0 0 0 0-4zM12 7v10",
  busca: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 20l-4-4",
  coracao: "M12 20s-7-4.5-7-10a4 4 0 0 1 7-2.5A4 4 0 0 1 19 10c0 5.5-7 10-7 10z",
  calendario: "M5 6h14v14H5zM5 10h14M9 4v4M15 4v4",
  relogio: "M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16zM12 8v4l3 2",
  dir: "M10 6l6 6-6 6",
  esq: "M14 6l-6 6 6 6",
  baixo: "M7 10l5 5 5-5",
  x: "M7 7l10 10M17 7L7 17",
};
export function Icone({ nome, tamanho = 18 }: { nome: keyof typeof ICONES; tamanho?: number }) {
  return (
    <svg width={tamanho} height={tamanho} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={ICONES[nome]} />
    </svg>
  );
}

function Poster({ filme, className }: { filme: Filme; className?: string }) {
  // O thumbnail é gerado pelo worker; até ele existir, usa o original.
  return (
    <img className={className} alt={filme.titulo} src={filme.thumb_url ?? ""}
      onError={(e) => { if (filme.poster_url && e.currentTarget.src !== filme.poster_url) e.currentTarget.src = filme.poster_url; }} />
  );
}

export default function App() {
  const [filmes, setFilmes] = useState<Filme[]>([]);
  const [filmeId, setFilmeId] = useState<number>();
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState(iso(new Date()));
  const [sessaoId, setSessaoId] = useState<number>();
  const [assentos, setAssentos] = useState<Assentos>(VAZIO);
  const [busca, setBusca] = useState<string>();
  const [aviso, setAviso] = useState<{ texto: string; ok?: boolean }>();
  const dialogo = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    api<{ filmes: Filme[] }>("/catalogo")
      .then((c) => { setFilmes(c.filmes); setFilmeId(c.filmes[0]?.id); })
      .catch((e) => setAviso({ texto: `Não foi possível carregar o catálogo: ${erroMsg(e)}` }));
  }, []);

  const filme = filmes.find((f) => f.id === filmeId);
  const sessoesDoDia = useMemo(() => filme?.sessoes.filter((s) => s.data === data) ?? [], [filme, data]);
  const sessao = sessoesDoDia.find((s) => s.id === sessaoId);
  const visiveis = filmes.filter((f) => !busca || f.titulo.toLowerCase().includes(busca.toLowerCase()));
  const dias = Array.from({ length: 7 }, (_, i) => { const d = new Date(); d.setDate(d.getDate() + offset + i); return d; });

  useEffect(() => { setSessaoId(sessoesDoDia[0]?.id); }, [sessoesDoDia]);

  const carregarAssentos = useCallback(() => {
    if (!sessaoId) return setAssentos(VAZIO);
    api<Assentos>(`/sessoes/${sessaoId}/assentos?client_id=${clientId}`).then(setAssentos).catch(() => {});
  }, [sessaoId]);

  useEffect(() => {
    carregarAssentos();
    const t = setInterval(carregarAssentos, 5000);
    return () => clearInterval(t);
  }, [carregarAssentos]);

  async function alternar(a: string) {
    if (!sessao) return;
    try {
      if (assentos.meus.includes(a)) {
        await api(`/sessoes/${sessao.id}/reservas/${a}?client_id=${clientId}`, { method: "DELETE" });
      } else {
        await api(`/sessoes/${sessao.id}/reservas`, { method: "POST", body: JSON.stringify({ assento: a, client_id: clientId }) });
      }
      setAviso(undefined);
    } catch (e) {
      setAviso({ texto: erroMsg(e) });
    }
    carregarAssentos();
  }

  async function comprar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!sessao) return;
    const f = new FormData(e.currentTarget);
    try {
      const r = await api<{ assentos: string[]; total: number }>("/compras", {
        method: "POST",
        body: JSON.stringify({ sessao_id: sessao.id, assentos: meus, nome: f.get("nome"), email: f.get("email"), client_id: clientId }),
      });
      setAviso({ ok: true, texto: `Compra confirmada: ${r.assentos.join(", ")} · ${brl(r.total)}` });
      dialogo.current?.close();
    } catch (err) {
      setAviso({ texto: erroMsg(err) });
      dialogo.current?.close();
    }
    carregarAssentos();
  }

  const meus = [...assentos.meus].sort(ordemAssento);
  const ocupados = new Set([...assentos.vendidos, ...assentos.reservados]);
  const total = meus.length * (sessao?.preco ?? 0);

  return (
    <div className="painel">
      <header className="topo">
        <div className="topo-lado">
          <button className="icone-btn" aria-label="Menu"><Icone nome="menu" /></button>
          <button className="icone-btn" aria-label="Filtros"><Icone nome="filtro" /></button>
          {busca === undefined ? (
            <>
              <span className="chip chip-cheio">Novos <Icone nome="baixo" tamanho={16} /></span>
              <span className="chip">A partir de R$ 10 <Icone nome="x" tamanho={12} /></span>
              {filme && <span className="chip">{filme.titulo} <Icone nome="x" tamanho={12} /></span>}
            </>
          ) : (
            <input className="busca" autoFocus placeholder="Buscar filme..." value={busca}
              onChange={(e) => setBusca(e.target.value)} onKeyDown={(e) => e.key === "Escape" && setBusca(undefined)} />
          )}
        </div>
        <h1 className="logo">Cinematix</h1>
        <div className="topo-lado direita">
          <a className="icone-btn" href="#/admin" title="Gerenciar"><Icone nome="ingresso" /></a>
          <button className="icone-btn" aria-label="Buscar" onClick={() => setBusca(busca === undefined ? "" : undefined)}>
            <Icone nome={busca === undefined ? "busca" : "x"} />
          </button>
          <button className="icone-btn" aria-label="Favoritos"><Icone nome="coracao" /></button>
          <span className="avatar">C</span>
        </div>
      </header>

      <section className="datas">
        <span className="icone-btn quadrado"><Icone nome="calendario" /></span>
        {dias.map((d) => (
          <button key={iso(d)} className={`dia ${iso(d) === data ? "ativo" : ""}`} onClick={() => setData(iso(d))}>
            <small>{diaSemana(d)}</small>
            <strong>{d.getDate()}</strong>
          </button>
        ))}
        <div className="setas">
          <button className="icone-btn" aria-label="Próxima semana" onClick={() => setOffset(offset + 7)}><Icone nome="dir" /></button>
          <button className="icone-btn" aria-label="Semana anterior" disabled={offset === 0} onClick={() => setOffset(offset - 7)}><Icone nome="esq" /></button>
        </div>
      </section>

      <section className="faixa">
        {visiveis.map((f) => (
          <button key={f.id} className={`faixa-item ${f.id === filmeId ? "ativo" : ""}`} onClick={() => setFilmeId(f.id)}>
            <Poster filme={f} />
            <span>{f.titulo}</span>
          </button>
        ))}
        {visiveis.length === 0 && <p className="mudo">Nenhum filme encontrado.</p>}
      </section>

      <main className="conteudo">
        <section className="esquerda">
          {filme && (
            <div className="filme">
              <Poster filme={filme} className="poster" />
              <div>
                <h2>{filme.titulo}</h2>
                <p className="meta">{[filme.ano, duracao(filme.duracao_min)].filter(Boolean).join(" · ")}</p>
                <p className="sinopse">{filme.sinopse}</p>
                <dl className="notas">
                  {filme.imdb && <div><dt>IMDb</dt><dd>{filme.imdb}</dd></div>}
                  {filme.letterboxd && <div><dt>Letterboxd</dt><dd>{filme.letterboxd}</dd></div>}
                  {filme.critica && <div><dt>Crítica</dt><dd>{filme.critica}</dd></div>}
                </dl>
              </div>
            </div>
          )}

          <hr />
          <h3 className="rotulo"><Icone nome="relogio" tamanho={15} /> Horário</h3>
          <div className="horarios">
            {sessoesDoDia.map((s) => (
              <button key={s.id} className={`horario ${s.id === sessaoId ? "ativo" : ""}`} onClick={() => setSessaoId(s.id)}>
                {s.hora}
              </button>
            ))}
            {sessoesDoDia.length === 0 && <p className="mudo">Sem sessões neste dia.</p>}
          </div>

          <h3 className="rotulo"><Icone nome="ingresso" tamanho={15} /> Ingressos selecionados</h3>
          <div className="ingressos">
            {meus.map((a) => (
              <div key={a} className="ingresso">
                <strong>{a[0]}</strong><small>fileira</small>
                <strong>{a.slice(1).padStart(2, "0")}</strong><small>assento</small>
                <span className="preco">{brl(sessao?.preco ?? 0)}</span>
                <button className="remover" aria-label={`Remover ${a}`} onClick={() => alternar(a)}><Icone nome="x" tamanho={14} /></button>
              </div>
            ))}
            {meus.length === 0 && <p className="mudo">Escolha seus lugares no mapa. A reserva vale por 5 minutos.</p>}
          </div>

          {aviso && <p className={`aviso ${aviso.ok ? "ok" : ""}`}>{aviso.texto}</p>}

          <div className="rodape">
            <p className="total">Total - <span>{brl(total)}</span></p>
            <button className="comprar" disabled={meus.length === 0} onClick={() => dialogo.current?.showModal()}>Comprar</button>
          </div>
        </section>

        <section className="direita-mapa">
          <div className="tela">
            <svg viewBox="0 0 540 40" preserveAspectRatio="none"><path d="M2 38 Q270 -10 538 38" /></svg>
            <span>TELA</span>
          </div>
          <div className="mapa">
            {FILEIRAS.map((f) => (
              <div key={f} className="fileira">
                <span className="letra">{f}</span>
                {LUGARES.map((n) => {
                  const a = `${f}${n}`;
                  const estado = assentos.meus.includes(a) ? "selecionado" : ocupados.has(a) ? "ocupado" : "livre";
                  return (
                    <button key={a} className={`assento ${estado}`} disabled={!sessao || estado === "ocupado"}
                      aria-label={`Assento ${a}`} onClick={() => alternar(a)}>{n}</button>
                  );
                })}
                <span className="letra">{f}</span>
              </div>
            ))}
          </div>
          <div className="legenda">
            <span><i className="assento selecionado" /> Selecionado</span>
            <span><i className="assento livre" /> Disponível</span>
            <span><i className="assento ocupado" /> Ocupado</span>
          </div>
        </section>
      </main>

      <dialog ref={dialogo} className="dialogo">
        <form onSubmit={comprar}>
          <h3>Finalizar compra</h3>
          <p className="mudo">{filme?.titulo} · {sessao?.data.split("-").reverse().join("/")} {sessao?.hora} · {meus.join(", ")}</p>
          <label>Nome<input name="nome" required maxLength={120} /></label>
          <label>E-mail<input name="email" type="email" required maxLength={200} /></label>
          <p className="total">Total - <span>{brl(total)}</span></p>
          <div className="acoes">
            <button type="button" className="secundario" onClick={() => dialogo.current?.close()}>Cancelar</button>
            <button className="comprar">Confirmar</button>
          </div>
        </form>
      </dialog>
    </div>
  );
}
