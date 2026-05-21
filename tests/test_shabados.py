from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from khoji.retriever import KhojiIndex
from khoji.shabados import export_shabads_jsonl, inspect_shabados_v4, load_shabados_v4


class ShabadOsImportTests(unittest.TestCase):
    def test_loads_v4_database_shape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "fixture.sqlite"
            _create_fixture(db_path)

            shabads = load_shabados_v4(db_path)

            self.assertEqual(len(shabads), 1)
            self.assertEqual(shabads[0].shabad_id, "SGGS:AAA")
            self.assertEqual(shabads[0].ang, 684)
            self.assertEqual(shabads[0].raag, "Dhanaasree")
            self.assertEqual(shabads[0].author, "Guru Tegh Bahadur")
            self.assertEqual(shabads[0].lines[0].line_id, "SGGS:L001")
            self.assertEqual(shabads[0].lines[0].transliteration, "kahe re ban khojan jai")
            self.assertEqual(
                shabads[0].lines[1].metadata["translations"][0]["source"],
                "Dr. Sant Singh Khalsa",
            )

    def test_exported_shabados_corpus_works_with_retriever(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "fixture.sqlite"
            output_path = Path(directory) / "sggs.jsonl"
            _create_fixture(db_path)

            shabads = load_shabados_v4(db_path)
            export_shabads_jsonl(shabads, output_path)

            index = KhojiIndex(shabads)
            result = index.identify("sarab nivasi sada alepa")
            self.assertEqual(result.best_shabad.shabad.shabad_id, "SGGS:AAA")
            self.assertEqual(result.best_line.line.line_id, "SGGS:L002")

    def test_inspects_reference_tables(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "fixture.sqlite"
            _create_fixture(db_path)

            info = inspect_shabados_v4(db_path)

            self.assertEqual(info["sources"][0]["name_english"], "Sri Guru Granth Sahib Ji")
            self.assertEqual(info["languages"][0]["name_english"], "English")


def _create_fixture(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        create table sources (
            id integer primary key,
            name_gurmukhi text not null,
            name_english text not null,
            length integer not null,
            page_name_english text not null,
            page_name_gurmukhi text not null
        );
        create table languages (
            id integer primary key,
            name_gurmukhi text not null,
            name_english text not null,
            name_international text
        );
        create table writers (
            id integer primary key,
            name_gurmukhi text not null,
            name_english text not null
        );
        create table sections (
            id integer primary key,
            name_gurmukhi text not null,
            name_english text not null,
            description text not null,
            start_page integer not null,
            end_page integer not null,
            source_id integer not null
        );
        create table subsections (
            id integer primary key,
            section_id integer not null,
            name_gurmukhi text not null,
            name_english text not null,
            start_page integer,
            end_page integer
        );
        create table shabads (
            id text primary key,
            source_id integer not null,
            writer_id integer not null,
            section_id integer not null,
            subsection_id integer,
            sttm_id integer,
            order_id integer not null
        );
        create table line_types (
            id integer primary key,
            name_gurmukhi text not null,
            name_english text not null
        );
        create table lines (
            id text primary key,
            shabad_id text not null,
            source_page integer not null,
            source_line integer,
            first_letters text,
            vishraam_first_letters text,
            gurmukhi text not null,
            pronunciation text,
            pronunciation_information text,
            type_id integer,
            order_id integer not null
        );
        create table transliterations (
            line_id text not null,
            language_id integer not null,
            transliteration text not null,
            primary key (line_id, language_id)
        );
        create table translation_sources (
            id integer primary key,
            name_gurmukhi text not null,
            name_english text not null,
            source_id integer not null,
            language_id integer not null
        );
        create table translations (
            line_id text not null,
            translation_source_id integer not null,
            translation text not null,
            additional_information json,
            primary key (line_id, translation_source_id)
        );
        """
    )
    connection.executescript(
        """
        insert into sources values
            (1, 'SRI gurU gRMQ swihb jI', 'Sri Guru Granth Sahib Ji', 1430, 'Ang', 'AMg');
        insert into languages values
            (1, 'AMgryzI', 'English', 'English'),
            (2, 'pMjwbI', 'Punjabi', 'ਪੰਜਾਬੀ');
        insert into writers values
            (1, 'mhlw 9', 'Guru Tegh Bahadur');
        insert into sections values
            (1, 'DnwsrI', 'Dhanaasree', '', 660, 695, 1);
        insert into line_types values
            (2, 'isrlyK', 'Sirlekh'),
            (3, 'rhwau', 'Rahao'),
            (4, 'pMkqI', 'Pankti');
        insert into shabads values
            ('AAA', 1, 1, 1, null, 1234, 10);
        insert into lines values
            ('L001', 'AAA', 684, 1, 'krbkj', null, 'kwhy ry bn Kojn jweI ]', null, null, 4, 100),
            ('L002', 'AAA', 684, 2, 'snsatss', null, 'srb invwsI sdw Alypw; qohI sMig smweI ]1] rhwau ]', null, null, 3, 101);
        insert into transliterations values
            ('L001', 1, 'kahe re ban khojan jai'),
            ('L002', 1, 'sarab nivasi sada alepa tohi sang samai rahao');
        insert into translation_sources values
            (1, 'Sant Singh', 'Dr. Sant Singh Khalsa', 1, 1),
            (2, 'Sahib Singh', 'Prof. Sahib Singh', 1, 2);
        insert into translations values
            ('L001', 1, 'Why do you go looking for Him in the forest?', null),
            ('L001', 2, 'ਹੇ ਭਾਈ! ਜੰਗਲ ਵਿਚ ਕਿਉਂ ਲੱਭਣ ਜਾਂਦਾ ਹੈਂ?', null),
            ('L002', 1, 'He is always detached and dwelling with you.', null),
            ('L002', 2, 'ਉਹ ਤੇਰੇ ਨਾਲ ਹੀ ਵੱਸਦਾ ਹੈ।', null);
        """
    )
    connection.commit()
    connection.close()


if __name__ == "__main__":
    unittest.main()

