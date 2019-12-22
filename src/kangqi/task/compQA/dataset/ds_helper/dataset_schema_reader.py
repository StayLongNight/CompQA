import codecs

from ..kq_schema import CompqSchema
from ...util.fb_helper import is_mediator_as_expect, get_domain, get_range, is_type_contained_by

from kangqi.util.LogUtil import LogInfo


""" Schema semantic quality control: code from debugging/general_two_hop_check.py """

schema_level_dict = {'strict': 0, 'elegant': 1, 'coherent': 2, 'general': 3}

#   strict: 1-hop or 2-hop with mediators found in "mediator.tsv"
#  elegent: allowing 2-hop where pred1.range == pred2.domain
# coherent: allowing 2-hop where pred1.range \in pred2.domain
#  general: allowing all the 2-hop schemas


def schema_classification(sc):
    for category, focus, pred_seq in sc.raw_paths:
        if category != 'Main':
            continue  # only consider main path
        # LogInfo.logs('pred-0: [%s], expected_type: [%s], is_med = [%s]',
        #              pred_seq[0], get_range(pred_seq[0]), is_mediator_as_expect(pred_seq[0]))
        if len(pred_seq) == 1:
            return 0
        elif is_mediator_as_expect(pred=pred_seq[0]):
            return 0
        else:
            p1_range = get_range(pred_seq[0])
            p2_domain = get_domain(pred_seq[1])
            if p1_range == p2_domain:
                return 1
            elif is_type_contained_by(p1_range, p2_domain):
                return 2
            else:
                return 3
    return 3


def load_schema_by_kqnew_protocol(q_idx, schema_fp, gather_linkings, sc_max_len, schema_level,
                                  sc_len_dist, path_len_dist, ans_size_dist,
                                  use_ans_type_dist=False, placeholder_policy='ActiveOnly',
                                  full_constr=True, fix_dir=True):
    """
    Read the schema files generated by KQ.
    Using the schema in kq_schema.py
    We read raw paths from json files, and convert them into path_list on-the-fly.
    Used after 12/05/2017.
    schema level: 0/1/2/3 (STRICT/ELEGANT/COHERENT/GENERAL)
    """
    LogInfo.logs('Schema level: %s', schema_level)
    LogInfo.logs('Use answer type distribution: %s', use_ans_type_dist)
    LogInfo.logs('Placeholder policy: %s', placeholder_policy)
    LogInfo.logs('Full constraint: %s', full_constr)
    LogInfo.logs('Fix constraint direction: %s', fix_dir)
    schema_level = schema_level_dict[schema_level]

    candidate_list = []
    with codecs.open(schema_fp, 'r', 'utf-8') as br:
        sc_lines = br.readlines()
        for ori_idx, sc_line in enumerate(sc_lines):
            sc = CompqSchema.read_schema_from_json(q_idx=q_idx, json_line=sc_line,
                                                   gather_linkings=gather_linkings,
                                                   use_ans_type_dist=use_ans_type_dist,
                                                   placeholder_policy=placeholder_policy,
                                                   full_constr=full_constr, fix_dir=fix_dir)
            sc.ori_idx = ori_idx + 1
            sc.construct_path_list()        # create the path_list on-the-fly
            """
                from the perspective of candidate searching in eff_candgen,
                since we treat main path and constraint path in different direction,
                there's no so-called duplicate schema at all.
                171226: Except for duplicate entities in EL results.
            """

            real_sc_len = len(sc.path_list)
            """ 180309: 
                It's more complex to count the real sc_len, 
                since we may introduce the answer type distribution.
            """
            ans_size_dist.append(sc.ans_size)
            sc_len_dist.append(len(sc.path_list))
            for raw_path, path in zip(sc.raw_paths, sc.path_list):
                path_len_dist.append(len(path))
                category = raw_path[0]
                if category == 'Type' and use_ans_type_dist:
                    real_sc_len -= 1        # ignore the explicit type constraint
            if use_ans_type_dist:
                real_sc_len += 1        # need one more line to represent the type distribution

            if real_sc_len <= sc_max_len and schema_classification(sc) <= schema_level:
                candidate_list.append(sc)
    return candidate_list, len(sc_lines)
