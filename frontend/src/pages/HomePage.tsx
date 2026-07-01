import { Button } from "@mantine/core";
import { motion } from "framer-motion";
import { Link } from "react-router-dom";

import { Blob } from "../components/Blob";
import { ArrowIcon, ChartIcon, FlaskIcon, UploadIcon } from "../components/icons";

interface OrbitChip {
  label: string;
  delay: number;
  top?: string;
  left?: string;
  right?: string;
  bottom?: string;
}

const fadeUp = {
  hidden: { opacity: 0, y: 22 },
  show: { opacity: 1, y: 0 },
};

const stagger = {
  hidden: {},
  show: { transition: { staggerChildren: 0.09, delayChildren: 0.05 } },
};

const FLOW = [
  {
    step: "01",
    to: "/ingest",
    icon: <UploadIcon />,
    title: "Inserir documentos",
    desc: "Envie seus textos. O Ditto os absorve, corta em trechos e gera os embeddings que viram sua memória.",
  },
  {
    step: "02",
    to: "/experiment",
    icon: <FlaskIcon />,
    title: "Gerar teste de qualidade",
    desc: "Combine estratégias de chunking, embedding, técnica de RAG e retriever sobre um conjunto de perguntas.",
  },
  {
    step: "03",
    to: "/results",
    icon: <ChartIcon />,
    title: "Resultados",
    desc: "Compare cada combinação por métricas de qualidade e descubra a forma ideal para os seus documentos.",
  },
];

const ORBIT: OrbitChip[] = [
  { label: "manual.pdf", top: "6%", left: "2%", delay: 0 },
  { label: "artigo.md", top: "20%", right: "0%", delay: 0.4 },
  { label: "notas.txt", bottom: "10%", left: "0%", delay: 0.8 },
  { label: "tese.txt", bottom: "0%", right: "8%", delay: 1.2 },
];

export function HomePage() {
  return (
    <motion.div variants={stagger} initial="hidden" animate="show">
      {/* ---------------- Hero ---------------- */}
      <section className="ditto-hero">
        <div>
          <motion.div variants={fadeUp} className="ditto-eyebrow">
            Adapta · Absorve · Especializa
          </motion.div>

          <motion.h1 variants={fadeUp} className="ditto-hero-title">
            Vire especialista
            <br />
            nos seus{" "}
            <span className="ditto-gradient-text">documentos.</span>
          </motion.h1>

          <motion.p variants={fadeUp} className="ditto-hero-sub">
            Como o Pokémon Ditto, ele assume a forma do que estuda: ingere seus
            textos, executa experimentos de RAG combinando estratégias e
            ranqueia tudo por qualidade — até virar especialista no seu acervo.
          </motion.p>

          <motion.div variants={fadeUp} className="ditto-hero-actions">
            <Button
              component={Link}
              to="/ingest"
              size="md"
              radius="md"
              variant="gradient"
              gradient={{ from: "#ab63f2", to: "#f26dcf", deg: 115 }}
              rightSection={<ArrowIcon />}
            >
              Começar a absorver
            </Button>
            <Button
              component={Link}
              to="/results"
              size="md"
              radius="md"
              variant="default"
            >
              Ver resultados
            </Button>
          </motion.div>
        </div>

        <motion.div variants={fadeUp} className="ditto-blob-stage">
          <div style={{ position: "relative" }}>
            <Blob size={300} />
            {ORBIT.map((chip) => (
              <motion.span
                key={chip.label}
                className="ditto-orbit-chip"
                style={{
                  top: chip.top,
                  left: chip.left,
                  right: chip.right,
                  bottom: chip.bottom,
                }}
                animate={{ y: [0, -10, 0] }}
                transition={{
                  duration: 4,
                  repeat: Infinity,
                  ease: "easeInOut",
                  delay: chip.delay,
                }}
              >
                {chip.label}
              </motion.span>
            ))}
          </div>
        </motion.div>
      </section>

      {/* ---------------- Combinatorial concept ---------------- */}
      <motion.div variants={fadeUp}>
        <div className="ditto-section-label">A forma é uma combinação</div>
        <div className="ditto-formula">
          <span className="ditto-formula-chip">chunking</span>
          <span className="ditto-formula-x">×</span>
          <span className="ditto-formula-chip">embedding</span>
          <span className="ditto-formula-x">×</span>
          <span className="ditto-formula-chip">técnica de RAG</span>
          <span className="ditto-formula-x">×</span>
          <span className="ditto-formula-chip">retriever</span>
        </div>
      </motion.div>

      {/* ---------------- How it works ---------------- */}
      <div className="ditto-section-label">Como funciona</div>
      <motion.div variants={stagger} className="ditto-flow">
        {FLOW.map((card) => (
          <motion.div key={card.to} variants={fadeUp}>
            <Link to={card.to} className="ditto-flow-card ditto-glass ditto-glass-hover">
              <span className="ditto-flow-step">{card.step}</span>
              <div className="ditto-flow-icon">{card.icon}</div>
              <h3 className="ditto-flow-title">{card.title}</h3>
              <p className="ditto-flow-desc">{card.desc}</p>
              <span className="ditto-flow-go">
                Abrir <ArrowIcon />
              </span>
            </Link>
          </motion.div>
        ))}
      </motion.div>
    </motion.div>
  );
}
