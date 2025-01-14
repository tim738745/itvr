/* eslint-disable react/jsx-indent */
import React, { useEffect } from 'react';
import Checkbox from '@mui/material/Checkbox';
import FormGroup from '@mui/material/FormGroup';
import FormControlLabel from '@mui/material/FormControlLabel';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import { useFormContext } from 'react-hook-form';

const ConsentGeneral = ({
  children,
  description = 'I understand that by submitting this application form it means:',
  title = '',
  subtitle = '',
  name
}) => {
  const { register, unregister, setValue, watch } = useFormContext();
  useEffect(() => {
    register(name);
    return () => {
      unregister(name);
    };
  }, [register, unregister, name]);
  const consent = watch(name);
  const commonStyles = {
    bgcolor: 'background.paper',
    width: '100%',
    height: '50vh',
    overflowY: 'scroll'
  };
  const emliAddress = (
    <address className="emli-address">
      Ministry of Energy, Mines and Low Carbon Innovation
      <br />
      Clean Transportation Branch
      <br />
      PO BOX 9314 Stn Prov Govt
      <br />
      Victoria, BC
      <br />
      V8W 9N1
      <br />
    </address>
  );
  return (
    <>
      <div>
        <h3>{title}</h3>
        <p>
          You must read the following statements and use the checkbox to
          indicate that you understand and agree.
        </p>
        <p>{subtitle}</p>
        <FormGroup>
          <FormControlLabel
            control={
              <Checkbox
                checked={consent}
                onChange={() =>
                  setValue(name, !consent, { shouldValidate: true })
                }
                inputProps={{ 'aria-label': 'controlled' }}
              />
            }
            className="label"
            label={
              <Typography variant="body2" color="textPrimary" fontWeight="bold">
                {description}
              </Typography>
            }
          />
        </FormGroup>
        <div className="box-container">
          <Box sx={{ ...commonStyles }}>
            {children}
            {emliAddress}
          </Box>
        </div>
      </div>
    </>
  );
};

export default ConsentGeneral;
