-- Clear stream URLs encrypted with unknown keys after SECRET_KEY env fix
UPDATE streams SET url = '';
UPDATE streams SET enabled = 0;
