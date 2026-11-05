/* =====================================================================
   Cielo animado + saludo según la hora local del visitante.

   - Madrugada 00:00–05:59 · Mañana 06:00–11:59 · Tarde 12:00–19:59 · Noche 20:00–23:59
   - El sol y la luna recorren un arco según la hora real; el color del cielo,
     las estrellas, las nubes y las luces de la ciudad se interpolan suavemente.
   - Vista previa: ?hora=22:30 fija la hora · ?demo=1 recorre el día en ~48 s.
   ===================================================================== */
(function () {
  "use strict";

  var params = new URLSearchParams(location.search);
  var movimientoReducido = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ------------------------------------------------------------ tiempo */
  var inicioReal = Date.now();
  var demo = params.has("demo");
  var VELOCIDAD_DEMO = 1800; // 1 s real = 30 min simulados
  var horaFija = null;
  var pHora = params.get("hora");
  if (pHora && /^\d{1,2}(:\d{2})?$/.test(pHora)) {
    var partes = pHora.split(":");
    var base = new Date();
    base.setHours(parseInt(partes[0], 10) % 24, parseInt(partes[1] || "0", 10), 0, 0);
    horaFija = base.getTime();
  }

  function ahora() {
    var transcurrido = (Date.now() - inicioReal) * (demo ? VELOCIDAD_DEMO : 1);
    return new Date((horaFija !== null ? horaFija : inicioReal) + transcurrido);
  }

  /* ---------------------------------------------------------- periodos */
  var ICONOS = {
    madrugada:
      '<svg viewBox="0 0 24 24"><path d="M14.5 3.5A8 8 0 1 0 20.5 15 6.5 6.5 0 0 1 14.5 3.5Z" fill="currentColor"/><circle cx="19" cy="5" r="1" fill="currentColor"/><circle cx="21.5" cy="9" r=".7" fill="currentColor"/></svg>',
    manana:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M7 17a5 5 0 0 1 10 0"/><path d="M3 17h2M19 17h2M12 7v3M5.6 10.6l1.4 1.4M18.4 10.6 17 12M3 21h18"/></svg>',
    tarde:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4" fill="currentColor"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
    noche:
      '<svg viewBox="0 0 24 24"><path d="M14.5 3.5A8 8 0 1 0 20.5 15 6.5 6.5 0 0 1 14.5 3.5Z" fill="currentColor"/></svg>',
  };

  var PERIODOS = {
    madrugada: {
      nombre: "Madrugada",
      saludo: "Buena madrugada",
      frase: "Turno de madrugada: tus servicios siguen bajo vigilancia mientras todos duermen.",
      login: "Gracias por conectarte a esta hora. El monitoreo nunca se detiene.",
      tema: "oscuro",
    },
    manana: {
      nombre: "Mañana",
      saludo: "Buenos días",
      frase: "Comienza el día con todos tus servicios a la vista.",
      login: "Que tengas una excelente jornada. Ingresa para revisar tus servicios.",
      tema: "claro",
    },
    tarde: {
      nombre: "Tarde",
      saludo: "Buenas tardes",
      frase: "Seguimos midiendo disponibilidad y latencia en tiempo real.",
      login: "Bienvenido de vuelta. Revisemos cómo van tus servicios esta tarde.",
      tema: "claro",
    },
    noche: {
      nombre: "Noche",
      saludo: "Buenas noches",
      frase: "La ciudad descansa; el monitoreo no.",
      login: "Bienvenido. Aunque sea de noche, aquí todo sigue en línea.",
      tema: "oscuro",
    },
  };

  function periodoDe(h) {
    if (h < 6) return "madrugada";
    if (h < 12) return "manana";
    if (h < 20) return "tarde";
    return "noche";
  }

  /* ------------------------------------------------------------ colores */
  // [hora, cénit, medio, horizonte]
  var PALETA = [
    [0.0, "#030617", "#0a1230", "#141c44"],
    [4.5, "#050a22", "#111a44", "#1d2550"],
    [5.75, "#16204f", "#3c3f7a", "#a0587a"],
    [6.75, "#3b5ba5", "#e09a7a", "#ffcf8f"],
    [8.0, "#4f8fe0", "#8cc2f2", "#d8ecff"],
    [12.5, "#2f7fe0", "#6db3f5", "#c6e6ff"],
    [17.0, "#3f86d6", "#86bde8", "#ffe2b8"],
    [19.25, "#3a4f9e", "#d9776a", "#ffb26b"],
    [20.25, "#1d2156", "#5a3c78", "#c0607a"],
    [21.25, "#0a0f2e", "#172052", "#2a2f63"],
    [24.0, "#030617", "#0a1230", "#141c44"],
  ];

  function rgb(hex) {
    var n = parseInt(hex.slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function mezclar(a, b, t) {
    var A = rgb(a), B = rgb(b);
    return "rgb(" + A.map(function (v, i) { return Math.round(v + (B[i] - v) * t); }).join(",") + ")";
  }
  function suave(t) {
    t = Math.min(1, Math.max(0, t));
    return t * t * (3 - 2 * t);
  }
  function campana(h, centro, ancho) {
    var d = h - centro;
    return Math.exp(-(d * d) / (2 * ancho * ancho));
  }

  function coloresCielo(h) {
    for (var i = 0; i < PALETA.length - 1; i++) {
      var a = PALETA[i], b = PALETA[i + 1];
      if (h >= a[0] && h < b[0]) {
        var t = suave((h - a[0]) / (b[0] - a[0]));
        return [mezclar(a[1], b[1], t), mezclar(a[2], b[2], t), mezclar(a[3], b[3], t)];
      }
    }
    return [PALETA[0][1], PALETA[0][2], PALETA[0][3]];
  }

  function nocturno(h) {
    if (h >= 21.25 || h < 4.5) return 1;
    if (h >= 19.5) return suave((h - 19.5) / 1.75);
    if (h < 6.25) return 1 - suave((h - 4.5) / 1.75);
    return 0;
  }

  function lucesCiudad(h) {
    if (h >= 20 || h < 6) return 1;
    if (h >= 18.75) return suave((h - 18.75) / 1.25);
    if (h < 7.25) return 1 - suave((h - 6) / 1.25);
    return 0;
  }

  var SALIDA_SOL = 6.25, PUESTA_SOL = 20.25;

  // El arco recorre la mitad derecha del cielo, donde no lo tapa el saludo.
  function arco(p) {
    return { x: 50 + p * 46, y: 84 - Math.sin(Math.PI * p) * 58 };
  }

  /* ---------------------------------------------------------- escena */
  function aleatorioConSemilla(semilla) {
    return function () {
      semilla = (semilla * 1664525 + 1013904223) % 4294967296;
      return semilla / 4294967296;
    };
  }

  function crearCiudad() {
    var r = aleatorioConSemilla(20261105);
    var NS = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 1440 140");
    svg.setAttribute("preserveAspectRatio", "xMidYMax slice");
    svg.setAttribute("class", "cielo__ciudad");

    function capa(clase, alturaMin, alturaMax, conVentanas) {
      var g = document.createElementNS(NS, "g");
      g.setAttribute("class", clase);
      var x = -10;
      while (x < 1450) {
        var ancho = 34 + r() * 62;
        var alto = alturaMin + r() * (alturaMax - alturaMin);
        var edif = document.createElementNS(NS, "rect");
        edif.setAttribute("x", x.toFixed(1));
        edif.setAttribute("y", (140 - alto).toFixed(1));
        edif.setAttribute("width", ancho.toFixed(1));
        edif.setAttribute("height", alto.toFixed(1));
        g.appendChild(edif);
        if (conVentanas) {
          for (var vy = 140 - alto + 8; vy < 132; vy += 11) {
            for (var vx = x + 6; vx < x + ancho - 8; vx += 10) {
              if (r() < 0.55) continue;
              var v = document.createElementNS(NS, "rect");
              v.setAttribute("x", vx.toFixed(1));
              v.setAttribute("y", vy.toFixed(1));
              v.setAttribute("width", "4");
              v.setAttribute("height", "5");
              v.setAttribute("class", "cielo__ventana" + (r() < 0.6 ? " encendida" : ""));
              g.appendChild(v);
            }
          }
        }
        x += ancho + 2 + r() * 10;
      }
      return g;
    }

    svg.appendChild(capa("cielo__edificios-lejos", 30, 80, false));

    // Torre de telecomunicaciones: el corazón de un sistema de monitoreo.
    var torre = document.createElementNS(NS, "g");
    torre.setAttribute("class", "cielo__torre");
    torre.innerHTML =
      '<path d="M1080 140 L1096 34 L1112 140 M1084 116 L1108 116 M1088 90 L1104 90 M1091 64 L1101 64 M1084 116 L1104 90 M1108 116 L1088 90 M1088 90 L1101 64 M1104 90 L1091 64" />' +
      '<line x1="1096" y1="34" x2="1096" y2="14" />' +
      '<circle class="cielo__baliza" cx="1096" cy="13" r="3.2" />' +
      '<path class="cielo__onda cielo__onda--1" d="M1084 8 A16 16 0 0 1 1108 8" />' +
      '<path class="cielo__onda cielo__onda--2" d="M1076 2 A26 26 0 0 1 1116 2" />';
    svg.appendChild(torre);

    svg.appendChild(capa("cielo__edificios-cerca", 22, 64, true));
    return svg;
  }

  function montar(el) {
    var frag = document.createDocumentFragment();
    function div(clase) {
      var d = document.createElement("div");
      d.className = clase;
      frag.appendChild(d);
      return d;
    }
    div("cielo__fondo");
    div("cielo__resplandor");
    var estrellas = div("cielo__estrellas");
    for (var i = 0; i < 110; i++) {
      var s = document.createElement("span");
      var tam = Math.random() < 0.85 ? 1 + Math.random() : 2 + Math.random();
      s.style.cssText =
        "left:" + (Math.random() * 100).toFixed(2) + "%;top:" + (Math.random() * 78).toFixed(2) +
        "%;width:" + tam.toFixed(1) + "px;height:" + tam.toFixed(1) +
        "px;animation-delay:" + (Math.random() * 5).toFixed(2) + "s;animation-duration:" +
        (2.5 + Math.random() * 4).toFixed(2) + "s";
      estrellas.appendChild(s);
    }
    var fugaz = div("cielo__fugaz");
    var sol = div("cielo__astro cielo__sol");
    var luna = div("cielo__astro cielo__luna");
    var nubes = div("cielo__nubes");
    [[12, 70, 1], [34, 95, 0.75], [58, 82, 1.1], [78, 120, 0.85], [92, 105, 0.65]].forEach(function (n, k) {
      var nube = document.createElement("span");
      nube.className = "cielo__nube";
      nube.style.cssText =
        "top:" + n[0] + "%;animation-duration:" + n[1] + "s;animation-delay:-" + (k * 23) + "s;--escala:" + n[2];
      nubes.appendChild(nube);
    });
    frag.appendChild(crearCiudad());
    el.appendChild(frag);
    return { el: el, sol: sol, luna: luna, fugaz: fugaz, ventanas: el.querySelectorAll(".cielo__ventana") };
  }

  /* ---------------------------------------------------- tema y saludo */
  var PREF_CLAVE = "monitor.tema";
  function preferenciaTema() {
    try { return localStorage.getItem(PREF_CLAVE) || "auto"; } catch (e) { return "auto"; }
  }
  function guardarPreferencia(v) {
    try { localStorage.setItem(PREF_CLAVE, v); } catch (e) { /* sin almacenamiento */ }
  }

  var periodoActual = null;
  var temaActual = null;

  function aplicarTema(periodo) {
    var pref = preferenciaTema();
    var tema = pref === "auto" ? PERIODOS[periodo].tema : pref;
    document.querySelectorAll("[data-tema-etiqueta]").forEach(function (e) {
      e.textContent = pref === "auto" ? "Auto" : pref === "claro" ? "Claro" : "Oscuro";
    });
    if (tema !== temaActual) {
      temaActual = tema;
      document.documentElement.setAttribute("data-tema", tema);
      document.dispatchEvent(new CustomEvent("cielo:tema", { detail: { tema: tema } }));
    }
  }

  function texto(selector, valor) {
    document.querySelectorAll(selector).forEach(function (e) {
      if (e.textContent !== valor) e.textContent = valor;
    });
  }

  function actualizarSaludo(fecha, h) {
    var periodo = periodoDe(h);
    texto("[data-reloj]", fecha.toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }));
    if (periodo === periodoActual) return;
    periodoActual = periodo;
    var p = PERIODOS[periodo];
    texto("[data-saludo]", p.saludo);
    texto("[data-frase]", p.frase);
    texto("[data-frase-login]", p.login);
    texto("[data-periodo-nombre]", p.nombre);
    var fechaLarga = fecha.toLocaleDateString("es-CL", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
    texto("[data-fecha]", fechaLarga.charAt(0).toUpperCase() + fechaLarga.slice(1));
    document.querySelectorAll("[data-periodo-icono]").forEach(function (e) { e.innerHTML = ICONOS[periodo]; });
    document.documentElement.setAttribute("data-periodo", periodo);
    aplicarTema(periodo);
    document.dispatchEvent(new CustomEvent("cielo:periodo", { detail: { periodo: periodo, info: p } }));
  }

  /* -------------------------------------------------------- render */
  function pintar(escena, h) {
    var st = escena.el.style;
    var c = coloresCielo(h);
    var noche = nocturno(h);
    st.setProperty("--cielo-1", c[0]);
    st.setProperty("--cielo-2", c[1]);
    st.setProperty("--cielo-3", c[2]);
    st.setProperty("--noche", noche.toFixed(3));
    st.setProperty("--luces", lucesCiudad(h).toFixed(3));
    st.setProperty("--resplandor", Math.max(campana(h, 6.6, 0.6), campana(h, 19.7, 0.6)).toFixed(3));
    st.setProperty("--edificio-lejos", mezclar("#b3c2dc", "#121838", noche));
    st.setProperty("--edificio-cerca", mezclar("#7b8fb3", "#070a1a", noche));
    st.setProperty("--nube", mezclar("#ffffff", "#3a4270", noche));

    var dia = h >= SALIDA_SOL && h <= PUESTA_SOL;
    var p, pos, visible;
    if (dia) {
      p = (h - SALIDA_SOL) / (PUESTA_SOL - SALIDA_SOL);
      pos = arco(p);
      visible = Math.min(1, Math.sin(Math.PI * p) * 5);
      escena.sol.style.left = pos.x + "%";
      escena.sol.style.top = pos.y + "%";
      escena.sol.style.opacity = visible;
      escena.sol.style.setProperty("--calidez", (1 - Math.sin(Math.PI * p)).toFixed(3));
      escena.luna.style.opacity = 0;
    } else {
      var hl = h < SALIDA_SOL ? h + 24 : h;
      p = (hl - PUESTA_SOL) / (24 - PUESTA_SOL + SALIDA_SOL);
      pos = arco(p);
      visible = Math.min(1, Math.sin(Math.PI * p) * 5);
      escena.luna.style.left = pos.x + "%";
      escena.luna.style.top = pos.y + "%";
      escena.luna.style.opacity = visible;
      escena.sol.style.opacity = 0;
    }
  }

  function parpadearVentanas(escena) {
    if (!escena.ventanas.length) return;
    for (var i = 0; i < 3; i++) {
      var v = escena.ventanas[Math.floor(Math.random() * escena.ventanas.length)];
      v.classList.toggle("encendida");
    }
  }

  function estrellaFugaz(escena, h) {
    if (nocturno(h) < 0.8 || movimientoReducido) return;
    var f = escena.fugaz;
    f.style.left = (15 + Math.random() * 55) + "%";
    f.style.top = (5 + Math.random() * 25) + "%";
    f.classList.remove("activa");
    void f.offsetWidth; // reinicia la animación
    f.classList.add("activa");
  }

  function iniciar() {
    var escenas = Array.prototype.map.call(document.querySelectorAll("[data-cielo]"), montar);
    if (demo) document.documentElement.classList.add("cielo-demo");

    function tick() {
      var f = ahora();
      var h = f.getHours() + f.getMinutes() / 60 + f.getSeconds() / 3600;
      actualizarSaludo(f, h);
      escenas.forEach(function (e) { pintar(e, h); });
      return h;
    }

    tick();
    requestAnimationFrame(function () {
      document.documentElement.classList.add("cielo-listo");
    });

    if (demo) {
      var ultimo = 0;
      (function bucle(t) {
        if (t - ultimo > 33) { tick(); ultimo = t; }
        requestAnimationFrame(bucle);
      })(0);
    } else {
      setInterval(tick, 1000);
    }

    if (!movimientoReducido) {
      setInterval(function () { escenas.forEach(parpadearVentanas); }, 2500);
      (function programarFugaz() {
        setTimeout(function () {
          var f = ahora();
          var h = f.getHours() + f.getMinutes() / 60;
          escenas.forEach(function (e) { estrellaFugaz(e, h); });
          programarFugaz();
        }, demo ? 2500 : 7000 + Math.random() * 12000);
      })();
    }

    document.querySelectorAll("[data-boton-tema]").forEach(function (b) {
      b.addEventListener("click", function () {
        var orden = ["auto", "claro", "oscuro"];
        var sig = orden[(orden.indexOf(preferenciaTema()) + 1) % orden.length];
        guardarPreferencia(sig);
        aplicarTema(periodoActual);
      });
    });
  }

  window.Cielo = {
    periodo: function () { return periodoActual; },
    tema: function () { return temaActual; },
    ahora: ahora,
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar);
  else iniciar();
})();
