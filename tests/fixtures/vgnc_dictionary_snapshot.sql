-- vgnc dictionary lookup tables (real snapshot)
--
-- Full real-data extract of the small lookup tables the query layer hardcodes values
--
--   database_resource: 31 rows
--   nomenclature_type: 4 rows
--   gene_status: 12 rows
--   change_type: 21 rows


-- database_resource

INSERT INTO `database_resource` (`id`, `db_name`, `db_display_name`, `url`, `external_link_template`, `priority`, `class`) VALUES ('1', 'ensembl_gene', 'Ensembl', 'http://www.ensembl.org', 'http://www.ensembl.org/id/###ID###', NULL, 'gene');
INSERT INTO `database_resource` (`id`, `db_name`, `db_display_name`, `url`, `external_link_template`, `priority`, `class`) VALUES ('10', 'orthomcl_hcop', 'OrthoMCL', 'http://www.orthomcl.org/orthomcl/', 'http://orthomcl.org/orthomcl/showRecord.do?name=SequenceRecordClasses.SequenceRecordClass&full_id=###TAX_B###|###ID_B###', NULL, 'hcop');
INSERT INTO `database_resource` (`id`, `db_name`, `db_display_name`, `url`, `external_link_template`, `priority`, `class`) VALUES ('11', 'panther_hcop', 'Panther', 'http://pantherdb.org/genes/', 'http://www.pantherdb.org/genes/gene.do?acc=###ID###', NULL, 'hcop');
INSERT INTO `database_resource` (`id`, `db_name`, `db_display_name`, `url`, `external_link_template`, `priority`, `class`) VALUES ('12', 'phylomedb_hcop', 'PhylomeDB', 'http://phylomedb.org/', 'http://phylomedb.org/?q=search_tree&seqid=###ID###', NULL, 'hcop');
INSERT INTO `database_resource` (`id`, `db_name`, `db_display_name`, `url`, `external_link_template`, `priority`, `class`) VALUES ('13', 'treefam_hcop', 'TreeFam', 'http://www.treefam.org/', 'http://www.treefam.org/family/###ID_B####tabview=tab1', NULL, 'hcop');
INSERT INTO `database_resource` (`id`, `db_name`, `db_display_name`, `url`, `external_link_template`, `priority`, `class`) VALUES ('14', 'hgnc_gene', 'HGNC', 'www.genenames.org/', 'http://www.genenames.org/cgi-bin/gene_symbol_report?hgnc_id=###ID###', NULL, 'gene');
INSERT INTO `database_resource` (`id`, `db_name`, `db_display_name`, `url`, `external_link_template`, `priority`, `class`) VALUES ('15', 'vega_gene', 'VEGA', 'http://vega.sanger.ac.uk/', 'http://vega.sanger.ac.uk/Homo_sapiens/geneview?db=core;gene=###ID###', NULL, 'mapping');
INSERT INTO `database_resource` (`id`, `db_name`, `db_display_name`, `url`, `external_link_template`, `priority`, `class`) VALUES ('16', 'pseudogene.org_gene', 'Pseudogene.org', 'http://tables.pseudogene.org/', 'http://tables.pseudogene.org/###ID###', NULL, 'mapping');
INSERT INTO `database_resource` (`id`, `db_name`, `db_display_name`, `url`, `external_link_template`, `priority`, `class`) VALUES ('17', 'chrom', 'Chrom', 'http://www.ensembl.org', 'http://www.ensembl.org/###SP###/Location/View?r=###CHR###:###START###-###END###', NULL, 'mapping');
INSERT INTO `database_resource` (`id`, `db_name`, `db_display_name`, `url`, `external_link_template`, `priority`, `class`) VALUES ('18', 'coordinates', 'Coordinates', NULL, NULL, NULL, 'mapping');
INSERT INTO `database_resource` (`id`, `db_name`, `db_display_name`, `url`, `external_link_template`, `priority`, `class`) VALUES ('19', 'ncbi_gene_search', 'NCBI Gene', 'http://www.ncbi.nlm.nih.gov/gene', 'http://www.ncbi.nlm.nih.gov/gene/?term=###ID###', NULL, 'search');
INSERT INTO `database_resource` (`id`, `db_name`, `db_display_name`, `url`, `external_link_template`, `priority`, `class`) VALUES ('2', 'ncbi_gene', 'NCBI', 'http://www.ncbi.nlm.nih.gov/gene', 'http://www.ncbi.nlm.nih.gov/gene/?term=###ID###', NULL, 'gene');
INSERT INTO `database_resource` (`id`, `db_name`, `db_display_name`, `url`, `external_link_template`, `priority`, `class`) VALUES ('20', 'ensembl_gene_search', 'Ensembl', 'http://www.ensembl.org', 'http://www.ensembl.org/###EnsSpecies###/geneview?db=core&gene=###ID###', NULL, 'search');
INSERT INTO `database_resource` (`id`, `db_name`, `db_display_name`, `url`, `external_link_template`, `priority`, `class`) VALUES ('21', 'ncbi_symbol_search', 'NCBI', 'http://www.ncbi.nlm.nih.gov', 'http://www.ncbi.nlm.nih.gov/gquery/?term=###ID###', NULL, 'search');
INSERT INTO `database_resource` (`id`, `db_name`, `db_display_name`, `url`, `external_link_template`, `priority`, `class`) VALUES ('22', 'vgnc_gene', 'VGNC', '/', '/gene#/symbol_report?id=###ID###', NULL, 'gene');
INSERT INTO `database_resource` (`id`, `db_name`, `db_display_name`, `url`, `external_link_template`, `priority`, `class`) VALUES ('23', 'pubmed', 'PubMed', 'http://www.ncbi.nlm.nih.gov/pubmed', 'http://www.ncbi.nlm.nih.gov/pubmed/###ID###', NULL, 'reference');
INSERT INTO `database_resource` (`id`, `db_name`, `db_display_name`, `url`, `external_link_template`, `priority`, `class`) VALUES ('24', 'bgd_gene', 'BGD', 'http://www.bovinegenome.org/', 'http://bovinegenome.org/genepages/btau40/genes/###ID###', NULL, 'gene');
INSERT INTO `database_resource` (`id`, `db_name`, `db_display_name`, `url`, `external_link_template`, `priority`, `class`) VALUES ('25', 'hgnc_ortholog', 'HGNC', 'https://www.genenames.org/', 'https://www.genenames.org/data/gene-symbol-report/#!/hgnc_id/###ID###', NULL, 'ortholog');
INSERT INTO `database_resource` (`id`, `db_name`, `db_display_name`, `url`, `external_link_template`, `priority`, `class`) VALUES ('26', 'uniprot_protein', 'UniProt', 'http://www.uniprot.org/', 'http://www.uniprot.org/uniprot/###ID###', NULL, 'protein');
INSERT INTO `database_resource` (`id`, `db_name`, `db_display_name`, `url`, `external_link_template`, `priority`, `class`) VALUES ('27', 'ensembl_provisional_gene', 'Ensembl', 'http://www.ensembl.org', 'http://www.ensembl.org/id/###ID###', NULL, 'gene');
INSERT INTO `database_resource` (`id`, `db_name`, `db_display_name`, `url`, `external_link_template`, `priority`, `class`) VALUES ('28', 'ncbi_provisional_gene', 'NCBI', 'http://www.ncbi.nlm.nih.gov/gene', 'http://www.ncbi.nlm.nih.gov/gene/?term=###ID###', NULL, 'gene');
INSERT INTO `database_resource` (`id`, `db_name`, `db_display_name`, `url`, `external_link_template`, `priority`, `class`) VALUES ('29', 'hgnc_provisional_ortholog', 'HGNC', 'https://www.genenames.org/', 'https://www.genenames.org/cgi-bin/gene_symbol_report?hgnc_id=###ID###', NULL, 'ortholog');
INSERT INTO `database_resource` (`id`, `db_name`, `db_display_name`, `url`, `external_link_template`, `priority`, `class`) VALUES ('3', 'ensembl_hcop', 'Ensembl', 'http://www.ensembl.org', 'http://www.ensembl.org/###SP###/multicontigview?s1=###ORTHSP###;g1=###ID_B###;g=###ID_A###', NULL, 'hcop');
INSERT INTO `database_resource` (`id`, `db_name`, `db_display_name`, `url`, `external_link_template`, `priority`, `class`) VALUES ('30', 'europe_pmc', 'Europe PMC', 'https://europepmc.org/', 'https://europepmc.org/abstract/###CLASS###/###ID###', NULL, 'reference');
INSERT INTO `database_resource` (`id`, `db_name`, `db_display_name`, `url`, `external_link_template`, `priority`, `class`) VALUES ('31', 'horde', 'HORDE', 'https://genome.weizmann.ac.il/horde', 'https://genome.weizmann.ac.il/horde/organism/card/symbol:###ID###/organism:###SPECIES###/', NULL, 'specialist');
INSERT INTO `database_resource` (`id`, `db_name`, `db_display_name`, `url`, `external_link_template`, `priority`, `class`) VALUES ('4', 'eggnog_hcop', 'EggNOG', 'http://eggnogdb.embl.de/#/app/home', 'http://eggnogdb.embl.de/#/app/results####ID###_datamenu', NULL, 'hcop');
INSERT INTO `database_resource` (`id`, `db_name`, `db_display_name`, `url`, `external_link_template`, `priority`, `class`) VALUES ('5', 'homologene_hcop', 'Homologene', 'http://www.ncbi.nlm.nih.gov/homologene/', 'http://www.ncbi.nlm.nih.gov/entrez/query.fcgi?cmd=Retrieve&db=homologene&dopt=HomoloGene&list_uids=###ID###\'', NULL, 'hcop');
INSERT INTO `database_resource` (`id`, `db_name`, `db_display_name`, `url`, `external_link_template`, `priority`, `class`) VALUES ('6', 'inparanoid_hcop', 'Inparanoid', 'http://inparanoid.sbc.su.se/cgi-bin/index.cgi', 'http://inparanoid.sbc.su.se/cgi-bin/gene_search.cgi?id=###ID_B###&idtype=proteinid&all_or_selection=selection&specieslist=###TAX_A###&scorelimit=0.05&.submit=Submit+Query&.cgifields=specieslist&.cgifields=idtype&.cgifields=all_or_selection', NULL, 'hcop');
INSERT INTO `database_resource` (`id`, `db_name`, `db_display_name`, `url`, `external_link_template`, `priority`, `class`) VALUES ('7', 'ncbi_hcop', 'NCBI', 'http://www.ncbi.nlm.nih.gov/gene/', 'http://www.ncbi.nlm.nih.gov/gene/?Term=ortholog_gene_###ID###[group]', NULL, 'hcop');
INSERT INTO `database_resource` (`id`, `db_name`, `db_display_name`, `url`, `external_link_template`, `priority`, `class`) VALUES ('8', 'oma_hcop', 'OMA', 'http://omabrowser.org/oma/home/', 'http://omabrowser.org/cgi-bin/gateway.pl?f=DisplayGroup&p1=###ID###', NULL, 'hcop');
INSERT INTO `database_resource` (`id`, `db_name`, `db_display_name`, `url`, `external_link_template`, `priority`, `class`) VALUES ('9', 'orthodb_hcop', 'OrthoDB', 'http://orthodb.org/', 'http://cegg.unige.ch/orthodb7/results?searchtext=###ID###&level=Metazoa&tree=Arth&swaptree=Meta\'', NULL, 'hcop');

-- nomenclature_type

INSERT INTO `nomenclature_type` (`id`, `type`) VALUES ('1', 'previous_symbol');
INSERT INTO `nomenclature_type` (`id`, `type`) VALUES ('2', 'previous_name');
INSERT INTO `nomenclature_type` (`id`, `type`) VALUES ('3', 'alias_symbol');
INSERT INTO `nomenclature_type` (`id`, `type`) VALUES ('4', 'alias_name');

-- gene_status

INSERT INTO `gene_status` (`id`, `status`, `display`) VALUES ('1', 'Pending', 'Pending');
INSERT INTO `gene_status` (`id`, `status`, `display`) VALUES ('10', 'Provisional', 'Provisional');
INSERT INTO `gene_status` (`id`, `status`, `display`) VALUES ('11', 'Auto Approved', 'Approved');
INSERT INTO `gene_status` (`id`, `status`, `display`) VALUES ('12', 'Cont Approved', 'Approved');
INSERT INTO `gene_status` (`id`, `status`, `display`) VALUES ('2', 'Symbol Withdrawn', 'Symbol Withdrawn');
INSERT INTO `gene_status` (`id`, `status`, `display`) VALUES ('3', 'Entry Withdrawn', 'Entry Withdrawn');
INSERT INTO `gene_status` (`id`, `status`, `display`) VALUES ('4', 'Reserved', 'Reserved');
INSERT INTO `gene_status` (`id`, `status`, `display`) VALUES ('5', 'Suspended', 'Suspended');
INSERT INTO `gene_status` (`id`, `status`, `display`) VALUES ('6', 'Approved', 'Approved');
INSERT INTO `gene_status` (`id`, `status`, `display`) VALUES ('7', 'Automated', 'Automated');
INSERT INTO `gene_status` (`id`, `status`, `display`) VALUES ('8', 'Deleted', 'Deleted');
INSERT INTO `gene_status` (`id`, `status`, `display`) VALUES ('9', 'Contributed', 'Contributed');

-- change_type

INSERT INTO `change_type` (`id`, `field_changed`) VALUES ('1', 'all');
INSERT INTO `change_type` (`id`, `field_changed`) VALUES ('10', 'restrict_symbol');
INSERT INTO `change_type` (`id`, `field_changed`) VALUES ('11', 'curated_xref');
INSERT INTO `change_type` (`id`, `field_changed`) VALUES ('12', 'deleted_xref');
INSERT INTO `change_type` (`id`, `field_changed`) VALUES ('13', 'reason_not_auto_approved');
INSERT INTO `change_type` (`id`, `field_changed`) VALUES ('14', 'sequence_added');
INSERT INTO `change_type` (`id`, `field_changed`) VALUES ('15', 'family_added');
INSERT INTO `change_type` (`id`, `field_changed`) VALUES ('16', 'symbol is a provisional CYP');
INSERT INTO `change_type` (`id`, `field_changed`) VALUES ('17', 'alias_name');
INSERT INTO `change_type` (`id`, `field_changed`) VALUES ('18', 'alias_symbol');
INSERT INTO `change_type` (`id`, `field_changed`) VALUES ('19', 'gene_comment_added');
INSERT INTO `change_type` (`id`, `field_changed`) VALUES ('2', 'status_id');
INSERT INTO `change_type` (`id`, `field_changed`) VALUES ('20', 'symbol is a provisional OR');
INSERT INTO `change_type` (`id`, `field_changed`) VALUES ('21', 'locus_type_conflict');
INSERT INTO `change_type` (`id`, `field_changed`) VALUES ('3', 'assigned_symbol');
INSERT INTO `change_type` (`id`, `field_changed`) VALUES ('4', 'assigned_name');
INSERT INTO `change_type` (`id`, `field_changed`) VALUES ('5', 'editor_id');
INSERT INTO `change_type` (`id`, `field_changed`) VALUES ('6', 'locus_type_id');
INSERT INTO `change_type` (`id`, `field_changed`) VALUES ('7', 'chr_id');
INSERT INTO `change_type` (`id`, `field_changed`) VALUES ('8', 'assigned_id');
INSERT INTO `change_type` (`id`, `field_changed`) VALUES ('9', 'restrict_name');
