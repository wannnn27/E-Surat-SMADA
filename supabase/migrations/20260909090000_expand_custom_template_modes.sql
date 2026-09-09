alter table esurat.custom_templates
    add column if not exists person_mode text not null default 'single',
    add column if not exists max_people integer;

alter table esurat.custom_templates
    drop constraint if exists custom_templates_category_check,
    drop constraint if exists custom_templates_person_mode_check,
    drop constraint if exists custom_templates_max_people_check;

alter table esurat.custom_templates
    add constraint custom_templates_category_check
        check (category in ('guru', 'murid', 'umum')),
    add constraint custom_templates_person_mode_check
        check (person_mode in ('none', 'single', 'multiple')),
    add constraint custom_templates_max_people_check
        check (max_people is null or max_people >= 2);
