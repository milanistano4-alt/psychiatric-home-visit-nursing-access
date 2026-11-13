"""Read all 47 official DBF files, preserving published totals and suppression.

No routing, service coverage or facility results are calculated. Nothing is
extracted to the production map. Numeric sums use 1/10,000 person units.
"""
from pathlib import Path
from collections import Counter
from decimal import Decimal
from datetime import datetime, timezone, timedelta
import csv, hashlib, io, json, re, struct, zipfile
from acquire import ROOT

SCALE = 10000

def dbf_rows(stream):
    head = stream.read(32)
    if len(head) != 32: raise ValueError('Truncated DBF header')
    count, header_size, record_size = struct.unpack_from('<IHH', head, 4)
    descriptor = stream.read(header_size - 32)
    fields, offset = {}, 1
    for pos in range(0, len(descriptor) - 1, 32):
        d = descriptor[pos:pos+32]
        if d[:1] == b'\r': break
        if len(d) != 32: raise ValueError('Truncated field descriptor')
        key = d[:11].split(b'\0')[0].decode('ascii')
        fields[key] = (offset, offset + d[16], chr(d[11]), d[17])
        offset += d[16]
    if offset != record_size: raise ValueError('Unexpected DBF record size')
    yield fields, count
    for _ in range(count):
        raw = stream.read(record_size)
        if len(raw) != record_size: raise ValueError('Truncated DBF record')
        if raw[:1] != b' ': raise ValueError('Deleted/unknown DBF record marker')
        yield raw
    # The DBF end marker is optional; a nonempty, unexpected tail is an error.
    tail = stream.read()
    if tail not in (b'', b'\x1a'): raise ValueError('Unexpected DBF tail')

def read_text(raw, field):
    return raw[field[0]:field[1]].decode('ascii').strip()

def scaled(raw, field):
    value = read_text(raw, field)
    if not value: raise ValueError('Missing numeric population is not zero')
    d = Decimal(value) * SCALE
    if not d.is_finite() or d < 0 or d != d.to_integral_value():
        raise ValueError('Unexpected precision/negative/nonfinite population')
    return int(d)

def main():
    source = ROOT/'sources/downloads/500m_mesh_2024_SHP.zip'
    national = zipfile.ZipFile(source)
    archives = [(int(m[1]), n) for n in national.namelist()
                if (m := re.search(r'_([0-9]{2})_SHP\.zip$', n))]
    if sorted(k for k, n in archives) != list(range(1, 48)):
        raise ValueError('National archive does not contain exactly 47 prefectures')
    # Compact, published area-level data retained in memory only.
    seen, owners, rows, schema = {}, {}, [], None
    first_mesh_signature = {}
    duplicates, conflicts = Counter(), []
    for pref, archive in sorted(archives):
        with zipfile.ZipFile(io.BytesIO(national.read(archive))) as z:
            name = next(n for n in z.namelist() if n.endswith('.dbf'))
            cpg = next(n for n in z.namelist() if n.endswith('.cpg'))
            row_count, flags, s_ptn, s_pt00 = 0, Counter(), 0, 0
            multi_admin, age_fail, ordinary_fail = 0, 0, 0
            with z.open(name) as f:
                iterator = dbf_rows(f); fields, expected = next(iterator)
                field_names = list(fields)
                if schema is None: schema = field_names
                if field_names != schema: raise ValueError('Prefecture DBF schemas differ')
                numeric = ['PTN_2020', 'PTN_2025', 'PT00_2025'] + [f'PT{i:02}_2025' for i in range(1, 21)]
                required = ['MESH_ID','SHICODE','HITOKU2025','GASSAN2025'] + numeric
                if any(n not in fields for n in required): raise ValueError('Missing required field')
                for raw in iterator:
                    row_count += 1
                    mesh = read_text(raw, fields['MESH_ID'])
                    admin = read_text(raw, fields['SHICODE'])
                    flag = read_text(raw, fields['HITOKU2025'])
                    target = read_text(raw, fields['GASSAN2025'])
                    if not re.fullmatch(r'\d{9}', mesh): raise ValueError('Invalid mesh ID')
                    if flag not in ('','*','@'): raise ValueError('Unknown suppression code')
                    if flag == '*' and not re.fullmatch(r'\d{9}', target): raise ValueError('Missing suppression destination')
                    if flag != '*' and target: raise ValueError('Destination attached to nonsuppressed mesh')
                    flags[flag or 'none'] += 1
                    admin_codes = re.findall(r'\d{5}', admin)
                    multi_admin += len(admin_codes) > 1
                    values = [scaled(raw, fields[n]) for n in numeric]
                    p2020, ptn, pt00, *ages = values
                    s_ptn += ptn; s_pt00 += pt00
                    # 21 rounded values contribute at most 10.5 scaled units.
                    age_fail += abs(sum(ages) - pt00) > 11
                    ordinary_fail += flag == '' and abs(ptn-pt00) > 1
                    if flag == '*' and (pt00 != 0 or any(ages)):
                        raise ValueError('Suppressed age field not zero as documented')
                    signature = hashlib.sha256((flag+'|'+target+'|'+','.join(map(str,values))).encode()).digest()[:16]
                    key = (pref, mesh)
                    if mesh in first_mesh_signature:
                        duplicates[pref] += 1
                        if signature != first_mesh_signature[mesh][0]: conflicts.append({'mesh_id':mesh,'prefecture_a':first_mesh_signature[mesh][1],'prefecture_b':pref})
                    else: first_mesh_signature[mesh] = (signature, pref)
                    if key in seen: raise ValueError('Duplicate within prefecture/mesh key')
                    seen[key] = (signature, ptn, pt00, flag, target)
            if row_count != expected: raise ValueError('DBF record count mismatch')
            rows.append({'pref_code':f'{pref:02}', 'records':row_count, 'schema_fields':len(schema),
                'no_suppression_flag':flags['none'],'suppressed_age_meshes':flags['*'],
                'aggregation_destinations':flags['@'],'multi_admin_meshes':multi_admin,
                'shared_mesh_id_records_with_other_prefectures':duplicates[pref],
                'PTN_2025_sum':str(Decimal(s_ptn)/SCALE),'PT00_2025_sum':str(Decimal(s_pt00)/SCALE),
                'age_sum_beyond_rounding_tolerance':age_fail,
                'ordinary_total_mismatch_beyond_tolerance':ordinary_fail,
                'cpg':z.read(cpg).decode().strip()})
        print(f'prefecture {pref:02}: records read; schema and population columns checked',flush=True)
    missing_dest, dest_flags, incoming = [], [], {}
    for key, (_, ptn, pt00, flag, dest) in seen.items():
        if flag == '*':
            dest_key = (key[0], dest)
            if dest_key not in seen: missing_dest.append(key)
            elif seen[dest_key][3] != '@': dest_flags.append(key)
            total, count = incoming.get(dest_key,(0,0))
            incoming[dest_key] = (total+ptn,count+1)
    group_fail, max_group_error = [], 0
    orphan_dest = []
    for key, (_, ptn, pt00, flag, dest) in seen.items():
        if flag != '@': continue
        extra, count = incoming.get(key,(0,0))
        if count == 0: orphan_dest.append(key)
        error = abs(pt00-(ptn+extra))
        max_group_error = max(max_group_error,error)
        # Inputs and the destination total are each independently rounded.
        tolerance = (count+3)//2
        if error > tolerance: group_fail.append({'pref_code':key[0],'mesh_id':key[1],'error_scaled':error,'members':count+1})
    out = ROOT/'audit'
    with (out/'population_47_audit.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    summary={'audited_jst':datetime.now(timezone(timedelta(hours=9))).isoformat(timespec='seconds'),
        'scope':'47-prefecture population input audit; no nursing-service coverage or optimization result',
        'prefecture_archives':len(rows),'unique_geographic_mesh_ids':len(first_mesh_signature),
        'prefecture_mesh_population_records':len(seen),
        'cross_prefecture_shared_mesh_id_records':sum(duplicates.values()),'cross_prefecture_different_population_records':len(conflicts),
        'cross_prefecture_mesh_id_handling':'preserve (pref_code, mesh_id) components; do not deduplicate population by mesh ID alone',
        'all_prefectures_same_schema':True,'age_sum_failures':sum(r['age_sum_beyond_rounding_tolerance'] for r in rows),
        'ordinary_total_mismatch_failures':sum(r['ordinary_total_mismatch_beyond_tolerance'] for r in rows),
        'missing_suppression_destinations':len(missing_dest),'destination_flag_failures':len(dest_flags),
        'aggregation_groups':len(incoming),'aggregation_group_conservation_failures':len(group_fail),
        'orphan_destinations':len(orphan_dest),'maximum_group_rounding_error_persons':str(Decimal(max_group_error)/SCALE),
        'field_decision':'PTN_2025 retains published total population at original mesh; PT00/age fields relocate suppressed populations to aggregation destinations. D0 and age-weighted D1 require different handling.',
        'national_population_sum_not_service_coverage':True}
    summary['critical_checks_passed'] = not (missing_dest or dest_flags or group_fail or orphan_dest or summary['age_sum_failures'] or summary['ordinary_total_mismatch_failures'])
    (out/'population_47_audit.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'population_47_exceptions.json').write_text(json.dumps({'cross_prefecture_different_population_records':conflicts,'missing_dest':missing_dest,'bad_dest_flag':dest_flags,'group_fail':group_fail,'orphan_dest':orphan_dest},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__ == '__main__': main()
