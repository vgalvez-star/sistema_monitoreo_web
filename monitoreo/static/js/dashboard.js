/* Panel principal: estado en vivo, tarjetas, gráfico y eventos. */
(function () {
  "use strict";

  var CSRF = document.querySelector('meta[name="csrf-token"]').content;
  var REFRESCO_MS = 10000;
  var estado = { sitios: [], seleccionado: null, ultimaCarga: null, puntos: null, escala: null, cargando: false };

  /* ------------------------------------------------------------ utilidades */
  function $(id) { return document.getElementById(id); }

  function esc(v) {
    return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function ms(v) {
    if (v == null) return "—";
    return v >= 1000 ? (v / 1000).toFixed(2) + " s" : Math.round(v) + " ms";
  }

  function hora(iso) {
    return new Date(iso).toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" });
  }

  function haceCuanto(iso) {
    if (!iso) return "sin chequeos";
    var s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
    if (s < 5) return "hace un momento";
    if (s < 60) return "hace " + s + " s";
    var m = Math.round(s / 60);
    if (m < 60) return "hace " + m + " min";
    return "hace " + Math.round(m / 60) + " h";
  }

  function toast(mensaje, tipo) {
    var t = document.createElement("div");
    t.className = "toast" + (tipo ? " toast--" + tipo : "");
    t.textContent = mensaje;
    $("toasts").appendChild(t);
    setTimeout(function () { t.remove(); }, 4200);
  }

  function api(url, opciones) {
    opciones = opciones || {};
    opciones.headers = Object.assign({ "X-CSRF-Token": CSRF, Accept: "application/json" }, opciones.headers || {});
    opciones.credentials = "same-origin";
    return fetch(url, opciones).then(function (r) {
      if (r.status === 401) { location.href = "/login"; throw new Error("Sesión expirada"); }
      if (r.status === 204) return null;
      return r.json().then(function (datos) {
        if (!r.ok) throw new Error(datos.error || "Error " + r.status);
        return datos;
      });
    });
  }

  var ETIQUETA = { OK: "OK", LENTO: "LENTO", ERROR: "CAÍDO", SIN_DATOS: "PENDIENTE" };

  /* ---------------------------------------------------------- sparkline */
  function sparkline(serie) {
    var puntos = serie.filter(function (p) { return p.ms != null && p.estado !== "ERROR"; });
    if (serie.length < 2) return '<svg class="sparkline" viewBox="0 0 100 38" aria-hidden="true"></svg>';
    var max = Math.max.apply(null, puntos.map(function (p) { return p.ms; }).concat([1]));
    var paso = 100 / (serie.length - 1);
    var linea = [], fallos = "";
    serie.forEach(function (p, i) {
      var x = (i * paso).toFixed(2);
      if (p.estado === "ERROR" || p.ms == null) {
        fallos += '<circle class="sparkline__fallo" cx="' + x + '" cy="35" r="1.6"/>';
      } else {
        linea.push(x + "," + (34 - (p.ms / max) * 30).toFixed(2));
      }
    });
    var area = linea.length > 1
      ? '<polygon class="sparkline__area" points="' + linea[0].split(",")[0] + ",38 " + linea.join(" ") + " " + linea[linea.length - 1].split(",")[0] + ',38"/>'
      : "";
    return '<svg class="sparkline" viewBox="0 0 100 38" preserveAspectRatio="none" aria-hidden="true">' + area +
      (linea.length > 1 ? '<polyline class="sparkline__linea" points="' + linea.join(" ") + '"/>' : "") + fallos + "</svg>";
  }

  /* ------------------------------------------------------------- render */
  function renderResumen(r) {
    $("kpi-total").textContent = r.total;
    $("kpi-ok").innerHTML = r.operativos + "<small>/" + r.total + "</small>";
    var inc = r.caidos + r.lentos;
    $("kpi-incidencias").textContent = inc;
    $("kpi-incidencias-nota").textContent = r.caidos + " caído" + (r.caidos === 1 ? "" : "s") + " · " + r.lentos + " lento" + (r.lentos === 1 ? "" : "s");
    $("kpi-incidencias").parentElement.classList.toggle("hay-incidencias", inc > 0);
    $("kpi-latencia").innerHTML = r.latencia_promedio_ms == null ? "—" : Math.round(r.latencia_promedio_ms) + "<small>ms</small>";
    $("kpi-uptime").innerHTML = r.uptime_24h == null ? "—" : r.uptime_24h.toFixed(r.uptime_24h === 100 ? 0 : 2) + "<small>%</small>";

    var g = $("estado-global"), texto, clase;
    if (r.total === 0) { texto = "Sin sitios configurados"; clase = ""; }
    else if (r.sin_datos === r.total) { texto = "Primer chequeo en curso…"; clase = ""; }
    else if (r.caidos > 0) { texto = r.caidos + (r.caidos === 1 ? " servicio caído" : " servicios caídos"); clase = "error"; }
    else if (r.lentos > 0) { texto = r.lentos + (r.lentos === 1 ? " servicio lento" : " servicios lentos"); clase = "lento"; }
    else { texto = "Todos los servicios operativos"; clase = "ok"; }
    g.className = "hero__estado estado-global" + (clase ? " estado-global--" + clase : "");
    g.querySelector(".estado-global__texto").textContent = texto;
  }

  function renderSitios() {
    var cont = $("sitios");
    if (!estado.sitios.length) {
      cont.innerHTML = '<div class="vacio">Aún no hay sitios. Usa <strong>Agregar sitio</strong> para empezar a monitorear.</div>';
      return;
    }
    cont.innerHTML = estado.sitios.map(function (s) {
      var clase = s.estado === "SIN_DATOS" ? "" : " tarjeta--" + s.estado.toLowerCase();
      var sel = s.id === estado.seleccionado ? " seleccionada" : "";
      return (
        '<article class="tarjeta' + clase + sel + '" data-id="' + s.id + '" tabindex="0" aria-label="' + esc(s.nombre) + ", " + ETIQUETA[s.estado] + '">' +
          '<div class="tarjeta__cabecera">' +
            '<span class="punto"></span>' +
            '<div class="tarjeta__titulos">' +
              '<p class="tarjeta__nombre">' + esc(s.nombre) + "</p>" +
              '<p class="tarjeta__url" title="' + esc(s.url) + '">' + esc(s.url.replace(/^https?:\/\//, "")) + "</p>" +
            "</div>" +
            '<span class="insignia insignia--' + s.estado.toLowerCase() + '">' + ETIQUETA[s.estado] + "</span>" +
          "</div>" +
          '<div class="metricas">' +
            '<div><p class="metrica__etiqueta">Latencia</p><p class="metrica__valor">' + ms(s.tiempo_ms) + "</p></div>" +
            '<div><p class="metrica__etiqueta">Uptime 24h</p><p class="metrica__valor">' + (s.uptime_24h == null ? "—" : s.uptime_24h.toFixed(s.uptime_24h === 100 ? 0 : 1) + "<small>%</small>") + "</p></div>" +
            '<div><p class="metrica__etiqueta">HTTP</p><p class="metrica__valor">' + (s.codigo_http || "—") + "</p></div>" +
          "</div>" +
          (s.estado === "ERROR" && s.error ? '<p class="tarjeta__error">' + esc(s.error) + "</p>" : sparkline(s.serie)) +
          '<div class="tarjeta__pie">' +
            '<span data-fecha-relativa="' + esc(s.fecha || "") + '">' + haceCuanto(s.fecha) + "</span>" +
            '<button class="boton-icono" type="button" data-eliminar="' + s.id + '" title="Dejar de monitorear" aria-label="Eliminar ' + esc(s.nombre) + '">' +
              '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v6M14 11v6"/></svg>' +
            "</button>" +
          "</div>" +
        "</article>"
      );
    }).join("");
  }

  function renderSelector() {
    var sel = $("selector-sitio");
    var actual = String(estado.seleccionado || "");
    sel.innerHTML = estado.sitios.map(function (s) {
      return '<option value="' + s.id + '">' + esc(s.nombre) + "</option>";
    }).join("");
    sel.value = actual;
  }

  function renderEventos(registros) {
    var lista = $("eventos");
    if (!registros.length) {
      lista.innerHTML = '<li class="evento"><span class="evento__hora">—</span><span class="evento__sitio">Esperando el primer chequeo…</span><span></span></li>';
      return;
    }
    lista.innerHTML = registros.map(function (e) {
      return (
        '<li class="evento">' +
          '<time class="evento__hora" datetime="' + esc(e.fecha) + '">' + hora(e.fecha) + "</time>" +
          '<span class="evento__sitio">' + esc(e.nombre) + (e.error ? "<small>" + esc(e.error) + "</small>" : "") + "</span>" +
          '<span class="evento__derecha"><span class="evento__ms">' + ms(e.tiempo_ms) + '</span><span class="insignia insignia--' + e.estado.toLowerCase() + '">' + ETIQUETA[e.estado] + "</span></span>" +
        "</li>"
      );
    }).join("");
  }

  /* ------------------------------------------------------------ gráfico */
  // Gráfico SVG propio: sin dependencias externas y con colores tomados del tema vía CSS.
  var NS = "http://www.w3.org/2000/svg";
  var UMBRAL = Number($("grafico").dataset.umbral) || null;

  function techoRedondo(v) {
    if (v <= 0) return 100;
    var pot = Math.pow(10, Math.floor(Math.log10(v)));
    var pasos = [1, 2, 2.5, 5, 10];
    for (var i = 0; i < pasos.length; i++) if (pasos[i] * pot >= v) return pasos[i] * pot;
    return 10 * pot;
  }

  function renderStats(puntos, validos) {
    var stats = $("grafico-stats");
    if (!validos.length) {
      stats.innerHTML = puntos.length ? "<span>Todas las mediciones del período fallaron</span>" : "";
      return;
    }
    var ord = validos.slice().sort(function (a, b) { return a - b; });
    var p95 = ord[Math.min(ord.length - 1, Math.floor(ord.length * 0.95))];
    var prom = validos.reduce(function (a, b) { return a + b; }, 0) / validos.length;
    stats.innerHTML =
      "<span>Promedio <strong>" + ms(prom) + "</strong></span>" +
      "<span>Mínimo <strong>" + ms(ord[0]) + "</strong></span>" +
      "<span>Máximo <strong>" + ms(ord[ord.length - 1]) + "</strong></span>" +
      "<span>P95 <strong>" + ms(p95) + "</strong></span>" +
      "<span>Fallos <strong>" + (puntos.length - validos.length) + "</strong> de " + puntos.length + "</span>";
  }

  function renderGrafico(puntos) {
    estado.puntos = puntos;
    var cont = $("grafico"), svg = $("grafico-svg");
    var ancho = cont.clientWidth, alto = cont.clientHeight;
    var M = { izq: 54, der: 12, arr: 14, aba: 28 };
    var w = ancho - M.izq - M.der, h = alto - M.arr - M.aba;
    svg.setAttribute("viewBox", "0 0 " + ancho + " " + alto);
    $("grafico-vacio").hidden = puntos.length > 0;

    var validos = puntos.filter(function (p) { return p.estado !== "ERROR" && p.tiempo_ms != null; })
      .map(function (p) { return p.tiempo_ms; });
    renderStats(puntos, validos);

    var maximo = techoRedondo(Math.max.apply(null, validos.concat([50])) * 1.15);
    var n = puntos.length;
    function x(i) { return M.izq + (n <= 1 ? w / 2 : (i / (n - 1)) * w); }
    function y(v) { return M.arr + h - (v / maximo) * h; }

    var html = '<defs><linearGradient id="g-area" x1="0" y1="0" x2="0" y2="1">' +
      '<stop offset="0" class="grafico__stop-1"/><stop offset="1" class="grafico__stop-2"/></linearGradient></defs>';

    // Rejilla y eje Y
    for (var k = 0; k <= 4; k++) {
      var v = (maximo / 4) * k, yy = y(v).toFixed(1);
      html += '<line class="grafico__rejilla" x1="' + M.izq + '" x2="' + (M.izq + w) + '" y1="' + yy + '" y2="' + yy + '"/>' +
        '<text class="grafico__eje" x="' + (M.izq - 10) + '" y="' + yy + '" text-anchor="end" dominant-baseline="middle">' + ms(v) + "</text>";
    }

    // Umbral de lentitud
    if (UMBRAL && UMBRAL <= maximo) {
      var yu = y(UMBRAL).toFixed(1);
      html += '<line class="grafico__umbral" x1="' + M.izq + '" x2="' + (M.izq + w) + '" y1="' + yu + '" y2="' + yu + '"/>';
    }

    // Eje X: ~6 etiquetas de hora
    if (n > 1) {
      var marcas = Math.min(6, n);
      for (var m = 0; m < marcas; m++) {
        var idx = Math.round((m / (marcas - 1)) * (n - 1));
        var ancla = m === 0 ? "start" : m === marcas - 1 ? "end" : "middle";
        html += '<text class="grafico__eje" x="' + x(idx).toFixed(1) + '" y="' + (alto - 8) + '" text-anchor="' + ancla + '">' +
          hora(puntos[idx].fecha).slice(0, 5) + "</text>";
      }
    }

    // Serie: se corta en cada fallo para no inventar datos.
    var tramos = [], actual = [];
    puntos.forEach(function (p, i) {
      if (p.estado === "ERROR" || p.tiempo_ms == null) { if (actual.length) tramos.push(actual); actual = []; }
      else actual.push([x(i), y(p.tiempo_ms)]);
    });
    if (actual.length) tramos.push(actual);
    var base = (M.arr + h).toFixed(1);
    tramos.forEach(function (t) {
      var linea = t.map(function (q) { return q[0].toFixed(1) + "," + q[1].toFixed(1); }).join(" ");
      if (t.length > 1) {
        html += '<polygon class="grafico__area" points="' + t[0][0].toFixed(1) + "," + base + " " + linea + " " + t[t.length - 1][0].toFixed(1) + "," + base + '"/>';
        html += '<polyline class="grafico__linea" points="' + linea + '"/>';
      } else {
        html += '<circle class="grafico__punto-solo" cx="' + t[0][0].toFixed(1) + '" cy="' + t[0][1].toFixed(1) + '" r="2.5"/>';
      }
    });

    // Fallos: marcas rojas sobre el eje
    puntos.forEach(function (p, i) {
      if (p.estado !== "ERROR") return;
      var cx = x(i), by = M.arr + h;
      html += '<path class="grafico__fallo" d="M' + (cx - 4).toFixed(1) + "," + by + " L" + cx.toFixed(1) + "," + (by - 7) + " L" + (cx + 4).toFixed(1) + "," + by + 'Z"/>';
    });

    html += '<line class="grafico__guia" id="grafico-guia" y1="' + M.arr + '" y2="' + (M.arr + h) + '" x1="0" x2="0" visibility="hidden"/>' +
      '<circle class="grafico__cursor" id="grafico-cursor" r="4.5" cx="0" cy="0" visibility="hidden"/>';
    svg.innerHTML = html;
    estado.escala = { x: x, y: y, izq: M.izq, w: w, n: n };
  }

  function moverCursor(ev) {
    var e = estado.escala, puntos = estado.puntos || [];
    if (!e || !puntos.length) return;
    var rect = $("grafico").getBoundingClientRect();
    var px = ev.clientX - rect.left;
    var i = e.n <= 1 ? 0 : Math.round(((px - e.izq) / e.w) * (e.n - 1));
    i = Math.max(0, Math.min(e.n - 1, i));
    var p = puntos[i], cx = e.x(i);
    var guia = $("grafico-guia"), cursor = $("grafico-cursor"), tip = $("grafico-tooltip");
    guia.setAttribute("x1", cx); guia.setAttribute("x2", cx); guia.setAttribute("visibility", "visible");
    var fallo = p.estado === "ERROR" || p.tiempo_ms == null;
    if (fallo) cursor.setAttribute("visibility", "hidden");
    else { cursor.setAttribute("cx", cx); cursor.setAttribute("cy", e.y(p.tiempo_ms)); cursor.setAttribute("visibility", "visible"); }
    tip.innerHTML = "<strong>" + hora(p.fecha) + "</strong>" +
      (fallo ? '<span class="grafico__tooltip-error">' + esc(p.error || "Sin respuesta") + "</span>"
             : "<span>" + ms(p.tiempo_ms) + " · HTTP " + (p.codigo_http || "—") + (p.estado === "LENTO" ? " · lento" : "") + "</span>");
    tip.hidden = false;
    var tw = tip.offsetWidth;
    tip.style.left = Math.max(0, Math.min(rect.width - tw, cx - tw / 2)) + "px";
  }

  function ocultarCursor() {
    ["grafico-guia", "grafico-cursor"].forEach(function (id) {
      var el = $(id); if (el) el.setAttribute("visibility", "hidden");
    });
    $("grafico-tooltip").hidden = true;
  }

  $("grafico").addEventListener("pointermove", moverCursor);
  $("grafico").addEventListener("pointerleave", ocultarCursor);
  var redimension;
  window.addEventListener("resize", function () {
    clearTimeout(redimension);
    redimension = setTimeout(function () { if (estado.puntos) renderGrafico(estado.puntos); }, 120);
  });

  /* ------------------------------------------------------------- carga */
  function cargarGrafico() {
    if (!estado.seleccionado) { renderGrafico([]); return Promise.resolve(); }
    return api("/api/serie/" + estado.seleccionado + "?limite=120").then(function (d) {
      renderGrafico(d.puntos);
    });
  }

  function cargar() {
    if (estado.cargando) return;
    estado.cargando = true;
    Promise.all([api("/api/status"), api("/api/historial?limite=7")])
      .then(function (res) {
        var st = res[0];
        estado.sitios = st.sitios;
        estado.ultimaCarga = Date.now();
        if (!estado.sitios.some(function (s) { return s.id === estado.seleccionado; })) {
          estado.seleccionado = estado.sitios.length ? estado.sitios[0].id : null;
        }
        renderResumen(st.resumen);
        renderSitios();
        renderSelector();
        renderEventos(res[1].registros);
        $("actualizado").textContent = "actualizado " + hora(new Date().toISOString());
        return cargarGrafico();
      })
      .catch(function (e) { toast("No se pudo actualizar: " + e.message, "error"); })
      .then(function () { estado.cargando = false; });
  }

  function seleccionar(id) {
    estado.seleccionado = id;
    document.querySelectorAll(".tarjeta").forEach(function (t) {
      t.classList.toggle("seleccionada", Number(t.dataset.id) === id);
    });
    $("selector-sitio").value = String(id);
    cargarGrafico();
  }

  /* ----------------------------------------------------------- eventos */
  $("sitios").addEventListener("click", function (ev) {
    var borrar = ev.target.closest("[data-eliminar]");
    if (borrar) {
      ev.stopPropagation();
      var id = Number(borrar.dataset.eliminar);
      var sitio = estado.sitios.find(function (s) { return s.id === id; });
      if (!confirm("¿Dejar de monitorear " + (sitio ? sitio.nombre : "este sitio") + "? Se borrará su historial.")) return;
      api("/api/sitios/" + id, { method: "DELETE" })
        .then(function () { toast("Sitio eliminado", "ok"); cargar(); })
        .catch(function (e) { toast(e.message, "error"); });
      return;
    }
    var tarjeta = ev.target.closest(".tarjeta[data-id]");
    if (tarjeta) seleccionar(Number(tarjeta.dataset.id));
  });

  $("sitios").addEventListener("keydown", function (ev) {
    if ((ev.key === "Enter" || ev.key === " ") && ev.target.matches(".tarjeta[data-id]")) {
      ev.preventDefault();
      seleccionar(Number(ev.target.dataset.id));
    }
  });

  $("selector-sitio").addEventListener("change", function (ev) { seleccionar(Number(ev.target.value)); });

  var dialogo = $("dialogo-sitio");
  var form = $("form-sitio");
  document.querySelector("[data-abrir-dialogo]").addEventListener("click", function () {
    form.reset();
    $("form-error").hidden = true;
    dialogo.showModal();
    form.url.focus();
  });
  document.querySelector("[data-cerrar-dialogo]").addEventListener("click", function () { dialogo.close(); });
  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var boton = form.querySelector('[type="submit"]');
    boton.disabled = true;
    api("/api/sitios", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: form.url.value, nombre: form.nombre.value }),
    })
      .then(function (s) {
        dialogo.close();
        toast("Monitoreando " + s.nombre, "ok");
        estado.seleccionado = s.id;
        cargar();
      })
      .catch(function (e) {
        $("form-error").textContent = e.message;
        $("form-error").hidden = false;
      })
      .then(function () { boton.disabled = false; });
  });

  // Textos "hace X s" sin pedir datos al servidor.
  setInterval(function () {
    document.querySelectorAll("[data-fecha-relativa]").forEach(function (e) {
      e.textContent = haceCuanto(e.dataset.fechaRelativa);
    });
  }, 5000);

  // Pausa cuando la pestaña no está visible.
  var temporizador = setInterval(cargar, REFRESCO_MS);
  document.addEventListener("visibilitychange", function () {
    clearInterval(temporizador);
    if (!document.hidden) { cargar(); temporizador = setInterval(cargar, REFRESCO_MS); }
  });

  if (document.readyState === "complete") cargar();
  else window.addEventListener("load", cargar);
})();
