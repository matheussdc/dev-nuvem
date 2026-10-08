import { FormEvent, ReactNode, useEffect, useState } from "react";
import { api, brl, erroMsg, Filme, Sessao } from "./api";
import { Icone } from "./App";

type Aba = "filmes" | "sessoes" | "compras" | "logs" | "stress";
type Ingresso = { id: number; filme: string; data: string; hora: string; assento: string; nome: string; email: string; preco: number; criado_em: string };
type Log = { id: string; acao: string; entidade?: string; dados: string; timestamp: string };

const ABAS: [Aba, string][] = [["filmes", "Filmes"], ["sessoes", "Sessões"], ["compras", "Compras"], ["logs", "Logs (DynamoDB)"], ["stress", "Stress de CPU"]];
const dataBr = (d: string) => d.split("-").reverse().join("/");

export default function Admin() {
  const [token, setToken] = useState(localStorage.getItem("adminToken"));
  const [aba, setAba] = useState<Aba>("filmes");
  const [filmes, setFilmes] = useState<Filme[]>([]);
  const [erro, setErro] = useState("");

  const recarregar = () => api<{ filmes: Filme[] }>("/catalogo").then((c) => setFilmes(c.filmes)).catch((e) => setErro(erroMsg(e)));
  useEffect(() => { if (token) recarregar(); }, [token]);

  // Executa uma ação do admin; 401 limpa a senha salva.
  async function exec<T>(f: () => Promise<T>) {
    setErro("");
    try { return await f(); } catch (e) {
      if ((e as { status?: number }).status === 401) { localStorage.removeItem("adminToken"); setToken(null); }
      setErro(erroMsg(e));
    }
  }

  if (!token) {
    return (
      <div className="painel admin">
        <form className="login" onSubmit={(e) => {
          e.preventDefault();
          const t = String(new FormData(e.currentTarget).get("senha"));
          localStorage.setItem("adminToken", t);
          setToken(t);
        }}>
          <h1 className="logo">Cinematix · Admin</h1>
          {erro && <p className="aviso">{erro}</p>}
          <label>Senha do admin<input name="senha" type="password" required autoFocus /></label>
          <button className="comprar">Entrar</button>
          <a href="#/">Voltar para a bilheteria</a>
        </form>
      </div>
    );
  }

  return (
    <div className="painel admin">
      <header className="topo">
        <a className="icone-btn" href="#/" title="Bilheteria"><Icone nome="esq" /></a>
        <h1 className="logo">Cinematix · Admin</h1>
        <button className="chip" onClick={() => { localStorage.removeItem("adminToken"); setToken(null); }}>Sair</button>
      </header>
      <nav className="abas">
        {ABAS.map(([id, nome]) => (
          <button key={id} className={`horario ${aba === id ? "ativo" : ""}`} onClick={() => setAba(id)}>{nome}</button>
        ))}
      </nav>
      {erro && <p className="aviso">{erro}</p>}
      {aba === "filmes" && <Filmes filmes={filmes} exec={exec} recarregar={recarregar} />}
      {aba === "sessoes" && <Sessoes filmes={filmes} exec={exec} recarregar={recarregar} />}
      {aba === "compras" && <Compras exec={exec} />}
      {aba === "logs" && <Logs exec={exec} />}
      {aba === "stress" && <Stress exec={exec} />}
    </div>
  );
}

type Exec = <T>(f: () => Promise<T>) => Promise<T | undefined>;

function Tabela({ cabecalho, children }: { cabecalho: string[]; children: ReactNode }) {
  return (
    <div className="tabela-wrap">
      <table className="tabela">
        <thead><tr>{cabecalho.map((c) => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

function Filmes({ filmes, exec, recarregar }: { filmes: Filme[]; exec: Exec; recarregar: () => void }) {
  const [editando, setEditando] = useState<Filme | null>(null);
  const [chave, setChave] = useState(0); // remonta o formulário para limpar os campos

  async function salvar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const bruto = new FormData(e.currentTarget);
    const form = new FormData();
    for (const [k, v] of bruto) if (v instanceof File ? v.size > 0 : v !== "") form.append(k, v); // vazio = não enviado
    const ok = await exec(() => api(editando ? `/admin/filmes/${editando.id}` : "/admin/filmes", { method: editando ? "PUT" : "POST", body: form }));
    if (ok) { setEditando(null); setChave(chave + 1); recarregar(); }
  }

  async function excluir(f: Filme) {
    if (!confirm(`Excluir "${f.titulo}" e todas as sessões dele?`)) return;
    if (await exec(() => api(`/admin/filmes/${f.id}`, { method: "DELETE" }))) recarregar();
  }

  return (
    <div className="admin-grid">
      <Tabela cabecalho={["", "Título", "Ano", "Duração", "Sessões", ""]}>
        {filmes.map((f) => (
          <tr key={f.id}>
            <td><img className="mini" src={f.thumb_url ?? ""} alt="" onError={(e) => { if (f.poster_url) e.currentTarget.src = f.poster_url; }} /></td>
            <td>{f.titulo}</td><td>{f.ano}</td><td>{f.duracao_min} min</td><td>{f.sessoes.length}</td>
            <td className="acoes-linha">
              <button className="chip" onClick={() => { setEditando(f); setChave(chave + 1); }}>Editar</button>
              <button className="chip perigo" onClick={() => excluir(f)}>Excluir</button>
            </td>
          </tr>
        ))}
      </Tabela>
      <form key={chave} className="formulario" onSubmit={salvar}>
        <h3>{editando ? `Editar: ${editando.titulo}` : "Novo filme"}</h3>
        <label>Título<input name="titulo" required maxLength={200} defaultValue={editando?.titulo} /></label>
        <div className="linha">
          <label>Ano<input name="ano" type="number" defaultValue={editando?.ano ?? ""} /></label>
          <label>Duração (min)<input name="duracao_min" type="number" defaultValue={editando?.duracao_min ?? ""} /></label>
        </div>
        <label>Sinopse<textarea name="sinopse" rows={4} defaultValue={editando?.sinopse} /></label>
        <div className="linha">
          <label>IMDb<input name="imdb" maxLength={20} placeholder="7,7/10" defaultValue={editando?.imdb} /></label>
          <label>Letterboxd<input name="letterboxd" maxLength={20} placeholder="3,8/5" defaultValue={editando?.letterboxd} /></label>
          <label>Crítica<input name="critica" maxLength={20} placeholder="91%" defaultValue={editando?.critica} /></label>
        </div>
        <label>Pôster {editando && "(deixe vazio para manter)"}<input name="poster" type="file" accept="image/*" required={!editando} /></label>
        <div className="acoes">
          {editando && <button type="button" className="secundario" onClick={() => { setEditando(null); setChave(chave + 1); }}>Cancelar</button>}
          <button className="comprar">Salvar</button>
        </div>
      </form>
    </div>
  );
}

function Sessoes({ filmes, exec, recarregar }: { filmes: Filme[]; exec: Exec; recarregar: () => void }) {
  const [filmeId, setFilmeId] = useState<number>();
  const [editando, setEditando] = useState<Sessao | null>(null);
  const [chave, setChave] = useState(0);
  const atual = filmeId ?? filmes[0]?.id;
  const sessoes = filmes.find((f) => f.id === atual)?.sessoes ?? [];

  async function salvar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const corpo = JSON.stringify({ filme_id: Number(f.get("filme_id")), data: f.get("data"), hora: f.get("hora"), preco: Number(f.get("preco")) });
    const ok = await exec(() => api(editando ? `/admin/sessoes/${editando.id}` : "/admin/sessoes", { method: editando ? "PUT" : "POST", body: corpo }));
    if (ok) { setEditando(null); setChave(chave + 1); recarregar(); }
  }

  async function excluir(s: Sessao) {
    if (!confirm(`Excluir a sessão de ${dataBr(s.data)} às ${s.hora}?`)) return;
    if (await exec(() => api(`/admin/sessoes/${s.id}`, { method: "DELETE" }))) recarregar();
  }

  return (
    <div className="admin-grid">
      <div>
        <select className="busca" value={atual} onChange={(e) => setFilmeId(Number(e.target.value))}>
          {filmes.map((f) => <option key={f.id} value={f.id}>{f.titulo}</option>)}
        </select>
        <Tabela cabecalho={["Data", "Hora", "Preço", ""]}>
          {sessoes.map((s) => (
            <tr key={s.id}>
              <td>{dataBr(s.data)}</td><td>{s.hora}</td><td>{brl(s.preco)}</td>
              <td className="acoes-linha">
                <button className="chip" onClick={() => { setEditando(s); setChave(chave + 1); }}>Editar</button>
                <button className="chip perigo" onClick={() => excluir(s)}>Excluir</button>
              </td>
            </tr>
          ))}
        </Tabela>
      </div>
      <form key={chave} className="formulario" onSubmit={salvar}>
        <h3>{editando ? "Editar sessão" : "Nova sessão"}</h3>
        <label>Filme
          <select name="filme_id" defaultValue={editando?.filme_id ?? atual}>
            {filmes.map((f) => <option key={f.id} value={f.id}>{f.titulo}</option>)}
          </select>
        </label>
        <div className="linha">
          <label>Data<input name="data" type="date" required defaultValue={editando?.data} /></label>
          <label>Hora<input name="hora" type="time" required defaultValue={editando?.hora} /></label>
        </div>
        <label>Preço (R$)<input name="preco" type="number" min="0.01" step="0.01" required defaultValue={editando?.preco} /></label>
        <div className="acoes">
          {editando && <button type="button" className="secundario" onClick={() => { setEditando(null); setChave(chave + 1); }}>Cancelar</button>}
          <button className="comprar">Salvar</button>
        </div>
      </form>
    </div>
  );
}

function Compras({ exec }: { exec: Exec }) {
  const [linhas, setLinhas] = useState<Ingresso[]>([]);
  useEffect(() => { exec(() => api<Ingresso[]>("/admin/ingressos")).then((r) => r && setLinhas(r)); }, []);
  return (
    <Tabela cabecalho={["#", "Filme", "Sessão", "Assento", "Comprador", "E-mail", "Preço", "Comprado em"]}>
      {linhas.map((i) => (
        <tr key={i.id}>
          <td>{i.id}</td><td>{i.filme}</td><td>{dataBr(i.data)} {i.hora}</td><td>{i.assento}</td>
          <td>{i.nome}</td><td>{i.email}</td><td>{brl(i.preco)}</td><td>{new Date(i.criado_em + "Z").toLocaleString("pt-BR")}</td>
        </tr>
      ))}
    </Tabela>
  );
}

function Logs({ exec }: { exec: Exec }) {
  const [logs, setLogs] = useState<Log[]>([]);
  const carregar = () => exec(() => api<Log[]>("/admin/logs")).then((r) => r && setLogs(r));
  useEffect(() => { carregar(); }, []);
  return (
    <>
      <button className="chip" onClick={carregar}>Atualizar</button>
      <Tabela cabecalho={["Hora", "Ação", "Entidade", "Dados"]}>
        {logs.map((l) => (
          <tr key={l.id}>
            <td>{new Date(l.timestamp).toLocaleString("pt-BR")}</td><td><b>{l.acao}</b></td><td>{l.entidade ?? "-"}</td>
            <td><code>{l.dados}</code></td>
          </tr>
        ))}
      </Tabela>
    </>
  );
}

function Stress({ exec }: { exec: Exec }) {
  const [segundos, setSegundos] = useState(180);
  const [disparos, setDisparos] = useState<{ instancia: string; cpus: number; segundos: number; hora: string }[]>([]);
  async function disparar() {
    const r = await exec(() => api<{ instancia: string; cpus: number; segundos: number }>(`/admin/stress?segundos=${segundos}`, { method: "POST" }));
    if (r) setDisparos([{ ...r, hora: new Date().toLocaleTimeString("pt-BR") }, ...disparos]);
  }
  return (
    <div className="formulario">
      <p className="mudo">
        Cada clique ocupa 100% das vCPUs da instância que o ALB escolher. Acima de 70% por 1 minuto o Auto Scaling
        lança outra instância (máx. 3). Clique de novo para atingir as novas; quando a carga acabar, ele volta para 1.
      </p>
      <div className="linha">
        <label>Duração (s)<input type="number" min={1} max={600} value={segundos} onChange={(e) => setSegundos(Number(e.target.value))} /></label>
        <button className="comprar" onClick={disparar}>Gerar carga</button>
      </div>
      <Tabela cabecalho={["Hora", "Instância", "vCPUs", "Duração"]}>
        {disparos.map((d, i) => <tr key={i}><td>{d.hora}</td><td>{d.instancia}</td><td>{d.cpus}</td><td>{d.segundos}s</td></tr>)}
      </Tabela>
    </div>
  );
}
