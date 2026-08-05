// Die.js File

import React, { Component } from 'react';
import './Die.css';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import type { IconName } from '@fortawesome/fontawesome-svg-core';

const FACE_NAMES = [
  'one',
  'two',
  'three',
  'four',
  'five',
  'six',
];

class Die extends Component<{
  face: number;
  rolling: boolean;
}> {
  render() {
    const { face, rolling } = this.props;
    const dieIcon = `dice-${FACE_NAMES[face - 1]}` as IconName;

    // Using font awesome icon to show
    // the exactnumber of dots
    return (
      <div>
        <FontAwesomeIcon
          icon={['fas', dieIcon]}
          className={`Die${rolling ? ' Die-shaking' : ''}`}
        />
      </div>
    );
  }
}

export default Die;
