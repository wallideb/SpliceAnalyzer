# hnRNP Enrichment Panel — Conditional References

When the hnRNP enrichment panel is rendered (i.e. `is_deep` is true and the
user includes section `"e"`), Appendix B of the PDF report appends an
extra block of 18 references after the always-emitted entries `[1]–[10]`.
Those entries are listed below as the canonical record (the source of truth
remains the bibliography block in
`rmats-viz/backend/app/routers/export.py`).

If the hnRNP panel is dropped or modified, this list — and the in-text
`[N]` placeholders in the hnRNP body section, the Appendix A methodology
subsection, and the Appendix C statistical-method subsection — must stay
synchronised.

---

## hnRNP-only references (numbering used in the source)

```
[11] Hwang JY, Jung S, Kook TL, Rouchka EC, Bok J, Park JW.
     rMAPS2: An update of the RNA map analysis and plotting server for
     alternative splicing regulation. Nucleic Acids Res. 2020;48(W1):W300-W306.

[12] Ray D, Kazan H, Cook KB, Weirauch MT, Najafabadi HS, Li X et al.
     A compendium of RNA-binding motifs for decoding gene regulation.
     Nature. 2013;499(7457):172-177.

[13] Martinez-Contreras R, Cloutier P, Shkreta L, Fisette JF, Revil T, Chabot B.
     hnRNP proteins and splicing control.
     Adv Exp Med Biol. 2007;623:123-147.

[14] Chkheidze AN, Lyakhov DL, Makeyev AV, Morales J, Kong J, Liebhaber SA.
     Assembly of the alpha-globin mRNA stability complex reflects binary
     interaction between the pyrimidine-rich 3' untranslated region
     determinant and poly(C) binding protein alphaCP.
     Mol Cell Biol. 1999;19(7):4572-4581.

[15] Makeyev AV, Liebhaber SA.
     The poly(C)-binding proteins: a multiplicity of functions and a search
     for mechanisms. RNA. 2002;8(3):265-278.

[16] Zhu J, Mayeda A, Krainer AR.
     Exon identity established through differential antagonism between exonic
     splicing silencer-bound hnRNP A1 and enhancer-bound SR proteins.
     Mol Cell. 2001;8(6):1351-1361.

[17] Damgaard CK, Tange TØ, Kjems J.
     hnRNP A1 controls HIV-1 mRNA splicing through cooperative binding to
     intron and exon splicing silencers in the context of a conserved
     secondary structure. RNA. 2002;8(11):1401-1415.

[18] Kashima T, Rao N, David CJ, Manley JL.
     hnRNP A1 functions with specificity in repression of SMN2 exon 7 splicing.
     Hum Mol Genet. 2007;16(24):3149-3159.

[19] Chen CD, Kobayashi R, Helfman DM.
     Binding of hnRNP H to an exonic splicing silencer is involved in the
     regulation of alternative splicing of the rat β-tropomyosin gene.
     Genes Dev. 1999;13(5):593-606.

[20] Erkelenz S, Mueller WF, Evans MS, Busch A, Schöneweis K, Hertel KJ,
     Schaal H. Position-dependent splicing activation and repression by SR
     and hnRNP proteins rely on common mechanisms. RNA. 2013;19(1):96-102.

[21] König J, Zarnack K, Rot G, Curk T, Kayikci M, Zupan B, Turner DJ,
     Luscombe NM, Ule J. iCLIP reveals the function of hnRNP particles in
     splicing at individual nucleotide resolution.
     Nat Struct Mol Biol. 2010;17(7):909-915.

[22] Zarnack K, König J, Tajnik M, Martincorena I, Eustermann S, Stévant I,
     Reyes A, Anders S, Luscombe NM, Ule J. Direct competition between hnRNP C
     and U2AF65 protects the transcriptome from the exonization of Alu elements.
     Cell. 2013;152(3):453-466.

[23] House AE, Lynch KW.
     An exonic splicing silencer represses spliceosome assembly after
     ATP-dependent exon recognition. Nat Struct Mol Biol. 2006;13(10):937-944.

[24] Hui J, Hung LH, Heiner M, Schreiner S, Neumüller N, Reither G, Haas SA,
     Bindereif A. Intronic CA-repeat and CA-rich elements: a new class of
     regulators of mammalian alternative splicing.
     EMBO J. 2005;24(11):1988-1998.

[25] Huelga SC, Vu AQ, Arnold JD, Liang TY, Liu PP, Yan BY, Donohue JP,
     Shiue L, Hoon S, Brenner S, Ares M Jr, Yeo GW.
     Integrative genome-wide analysis reveals cooperative regulation of
     alternative splicing by hnRNP proteins. Cell Rep. 2012;1(2):167-178.

[26] Xue Y, Zhou Y, Wu T, Zhu T, Ji X, Kwon YS, Zhang C, Yeo G, Black DL,
     Sun H, Fu XD, Zhang Y. Genome-wide analysis of PTB-RNA interactions
     reveals a strategy used by the general splicing repressor to modulate
     exon inclusion or skipping. Mol Cell. 2009;36(6):996-1006.

[27] Wagner EJ, Garcia-Blanco MA.
     Polypyrimidine tract binding protein antagonizes exon definition.
     Mol Cell Biol. 2001;21(10):3281-3288.

[28] Witten JT, Ule J.
     Understanding splicing regulation through RNA splicing maps.
     Trends Genet. 2011;27(3):89-97.
```

---

## Where each hnRNP reference is cited

- `[11]` Hwang 2020 — Section E body intro; Appendix A (hnRNP intro)
- `[12]` Ray 2013 — Appendix A (motif sources)
- `[13]` Martinez-Contreras 2006 — Appendix A (motif sources, hnRNP F/H row)
- `[14]` Chkheidze 1999 — Appendix A (hnRNP E motif provenance)
- `[15]` Makeyev 2002 — Appendix A (hnRNP E motif provenance)
- `[16]` Zhu 2001 — Appendix A regulatory-effect annotations (hnRNP A1/A2)
- `[17]` Damgaard 2002 — Appendix A regulatory-effect annotations (hnRNP A1/A2)
- `[18]` Kashima 2007 — Appendix A regulatory-effect annotations (hnRNP A1/A2)
- `[19]` Chen CD 1999 — Appendix A regulatory-effect annotations (hnRNP F/H)
- `[20]` Erkelenz 2013 — Appendix A regulatory-effect annotations (hnRNP F/H)
- `[21]` König 2010 — Appendix A regulatory-effect annotations (hnRNP C)
- `[22]` Zarnack 2013 — Appendix A regulatory-effect annotations (hnRNP C)
- `[23]` House 2006 — Appendix A regulatory-effect annotations (hnRNP L)
- `[24]` Hui 2005 — Appendix A regulatory-effect annotations (hnRNP L)
- `[25]` Huelga 2012 — Appendix A regulatory-effect annotations (hnRNP M)
- `[26]` Xue 2009 — Appendix A regulatory-effect annotations (PTB)
- `[27]` Wagner 2001 — Appendix A regulatory-effect annotations (PTB)
- `[28]` Witten 2011 — Appendix A regulatory-effect annotations (closing)
