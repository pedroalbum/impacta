"""Cliente autenticado da API do Mercado Livre.

ATENCAO - restricoes verificadas em 28/09/2026:
  * Nao existe grant_type=client_credentials. A doc oficial so aceita
    authorization_code e refresh_token, logo um humano PRECISA autorizar
    o app pelo browser na primeira vez.
  * access_token expira em 6h (21600s).
  * refresh_token e de USO UNICO e vale 6 meses: cada refresh devolve um novo
    e o anterior morre. Perder o ultimo obriga a refazer o fluxo no browser.
  * /items?ids= e /users?ids= estao descontinuados; a doc manda migrar para
    /items/bulk e /users/bulk ate 25/10/2026. Este cliente ja usa /bulk.
  * Paginacao por offset trava em 1000 registros; acima disso use
    search_type=scan (scroll_id expira em 5 min).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests

BASE = "https://api.mercadolibre.com"
AUTH = "https://auth.mercadolivre.com.br/authorization"
TOKENS = Path(os.getenv("MELI_TOKEN_STORE", "~/.config/meli/tokens.json")).expanduser()


class MeliClient:
    def __init__(self, app_id: str, secret: str, redirect_uri: str) -> None:
        self.app_id, self.secret, self.redirect_uri = app_id, secret, redirect_uri
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "meli-ml/0.1"
        self._tok: dict = self._carregar()

    # ---------- persistencia do token ----------
    def _carregar(self) -> dict:
        if TOKENS.exists():
            return json.loads(TOKENS.read_text())
        return {}

    def _salvar(self, tok: dict) -> None:
        tok["obtido_em"] = time.time()
        TOKENS.parent.mkdir(parents=True, exist_ok=True)
        TOKENS.write_text(json.dumps(tok, indent=2))
        TOKENS.chmod(0o600)  # contem refresh_token de 6 meses
        self._tok = tok

    # ---------- OAuth ----------
    def url_de_login(self, state: str = "meli-ml") -> str:
        return (f"{AUTH}?response_type=code&client_id={self.app_id}"
                f"&redirect_uri={self.redirect_uri}&state={state}")

    def trocar_code(self, code: str) -> None:
        """Roda UMA vez, com o code que volta na redirect_uri."""
        r = self.s.post(f"{BASE}/oauth/token", data={
            "grant_type": "authorization_code", "client_id": self.app_id,
            "client_secret": self.secret, "code": code,
            "redirect_uri": self.redirect_uri,
        }, timeout=30)
        r.raise_for_status()
        self._salvar(r.json())

    def _renovar(self) -> None:
        r = self.s.post(f"{BASE}/oauth/token", data={
            "grant_type": "refresh_token", "client_id": self.app_id,
            "client_secret": self.secret,
            "refresh_token": self._tok["refresh_token"],
        }, timeout=30)
        r.raise_for_status()
        self._salvar(r.json())  # o refresh_token novo substitui o usado

    @property
    def token(self) -> str:
        if not self._tok:
            raise RuntimeError(f"Sem token. Abra {self.url_de_login()} e chame trocar_code(code).")
        idade = time.time() - self._tok.get("obtido_em", 0)
        if idade > self._tok.get("expires_in", 21600) - 600:  # renova 10 min antes
            self._renovar()
        return self._tok["access_token"]

    # ---------- HTTP ----------
    def get(self, path: str, **params):
        for tentativa in range(5):
            r = self.s.get(f"{BASE}{path}", params=params or None, timeout=30,
                           headers={"Authorization": f"Bearer {self.token}"})
            if r.status_code == 429:  # local_rate_limited: nao ha numero oficial
                time.sleep(2 ** tentativa)
                continue
            if r.status_code == 401:
                self._renovar()
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError(f"Falhou apos retries: {path}")

    # ---------- coleta ----------
    def itens_do_vendedor(self, user_id: int, category: str | None = None) -> list[str]:
        """search_type=scan contorna o teto de 1000 do offset."""
        ids, scroll = [], None
        while True:
            p = {"search_type": "scan", "limit": 100}
            if category:
                p["category"] = category
            if scroll:
                p["scroll_id"] = scroll
            d = self.get(f"/users/{user_id}/items/search", **p)
            lote = d.get("results") or []
            ids.extend(lote)
            scroll = d.get("scroll_id")
            if not lote or not scroll:
                return ids

    def detalhes(self, item_ids: list[str], campos: list[str] | None = None) -> list[dict]:
        """/items/bulk aceita 20 ids por chamada. Em /bulk os campos exigem
        prefixo 'body.' e o status vem em 'status_code' (nao 'code')."""
        saida = []
        attrs = ",".join(f"body.{c}" for c in campos) if campos else None
        for i in range(0, len(item_ids), 20):
            p = {"ids": ",".join(item_ids[i:i + 20])}
            if attrs:
                p["attributes"] = attrs
            for reg in self.get("/items/bulk", **p) or []:
                if reg.get("status_code") == 200:
                    saida.append(reg.get("body", {}))
            time.sleep(0.2)
        return saida
