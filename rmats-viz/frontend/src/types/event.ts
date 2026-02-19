export type EventType = "SE" | "RI" | "A3SS" | "A5SS" | "MXE";

export interface SplicingEvent {
  id: string;
  analysis_id: string;
  event_type: EventType;
  rmats_id?: number | null;
  gene_id?: string | null;
  gene_symbol?: string | null;
  chr?: string | null;
  strand?: string | null;
  exon_start?: number | null;
  exon_end?: number | null;
  upstream_es?: number | null;
  upstream_ee?: number | null;
  downstream_es?: number | null;
  downstream_ee?: number | null;
  second_exon_start?: number | null;
  second_exon_end?: number | null;
  ijc_sample_1?: string | null;
  sjc_sample_1?: string | null;
  ijc_sample_2?: string | null;
  sjc_sample_2?: string | null;
  p_value?: number | null;
  fdr?: number | null;
  inc_level_1?: string | null;
  inc_level_2?: string | null;
  inc_level_difference?: number | null;
  abs_inc_level_diff?: number | null;
  top_rank?: number | null;
}

export interface EventsPage {
  items: SplicingEvent[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}
